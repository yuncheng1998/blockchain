import hashlib
import json
import requests
from textwrap import dedent
from time import time
from uuid import uuid4
from urllib.parse import urlparse
from argparse import ArgumentParser

from flask import Flask, jsonify, request

class Blockchain(object):

	def __init__(self):
		self.chain = []	#存储区块链
		self.current_transactions = []	#存储交易
		self.nodes = set() #使用set存储节点,防止添加重复节点
		self.new_block(previous_hash=1, proof=100) #构造一个创世块，proof为工作量证明

	def new_block(self, proof, previous_hash=None):
		#block信息构造 json格式
		block = {
			'index':len(self.chain)+1, 	#新块的索引
			'timestamp':time(),			#交易时间
			'transactions':self.current_transactions,	#本次交易的信息
			'proof':proof,				#工作量的证明
			'previous_hash':previous_hash or self.hash(self.chain[-1]),	#上一个区块的hash
		}

		self.current_transactions = [] 	#重置交易列表
		self.chain.append(block)		# 增加新区块
		return block  					#返回这个区块

	def new_transaction(self, sender, recipient, amount):
		# 将交易过的区块添加,返回下一个要被添加的block的索引
		self.current_transactions.append({
			'sender':sender,
			'recipient':recipient,
			'amount':amount,
			})
		return self.last_block['index']+1

	@staticmethod
	def hash(block):		#为block生成SHA-256 hash值
		block_string = json.dumps(block, sort_keys=True).encode() 	#json格式转换为string
		return hashlib.sha256(block_string).hexdigest()				#将string字符串SHA256加密
		

	@property
	def last_block(self):
		#返回最后一个区块
		return self.chain[-1]

	'''
	工作量证明
	查找一个p'使hash(pp') p'->当前proof, p->上一个proof

	'''
	def proof_of_work(self, last_proof):
		proof = 0
		while self.valid_proof(last_proof, proof) is False:
			proof += 1
		return proof

	@staticmethod
	def valid_proof(last_proof, proof):
		guess = str(last_proof+proof).encode()
		guess_hash = hashlib.sha256(guess).hexdigest()
		return guess_hash[:4] == '0000' #前4个元素是否为0

	def register_node(self, address):
		'''
		向节点列表中增加节点
		:param address: <str> 节点的地址 Eg. 'http://192.168.0.5:5000'
		:return: None
		'''
		parsed_url = urlparse(address)
		self.nodes.add(parsed_url.netloc) #netloc网址解析添加到节点列表中

	
	#检查是否为有效链，遍历每个区块的hash和proof进行验证
	def valid_chain(self, chain):
		last_block = chain[0]	#上一个区块
		current_index = 1		#当前区块  二者进行验证是否为有效
		while current_index < len(chain):
			block = chain[current_index]
			print(last_block)
			print(block)
			print("\n-----------\n")
			# Check that the hash of the block is correct
			if block['previous_hash'] != self.hash(last_block):
				return False
			# Check that the Proof of Work is correct
			if not self.valid_proof(last_block['proof'], block['proof']):
				return False
			last_block = block
			current_index += 1
		return True


	def resolve_conflicts(self):	
		"""
		共识算法解决冲突，发现最长的链就添加区块到自己的账本上
		:return: <bool> True 如果链被取代, 否则为False
		"""
		neighbours = self.nodes
		new_chain = None
		# 更改区块长度
		max_length = len(self.chain)
		# 验证所有邻节点的区块并验证，如果有效就加到自己链上
		for node in neighbours:
			response = requests.get('http://'+node+'/chain')
			if response.status_code == 200:
				length = response.json()['length']
				chain = response.json()['chain']
		# Check if the length is longer and the chain is valid
				if length > max_length and self.valid_chain(chain):
					max_length = length
					new_chain = chain
		# 增加自己的区块链上的区块
		if new_chain:
		    self.chain = new_chain
		    return True

		return False

	'''
	创建的API
	/transactions/new 	交易接口 创建一个交易添加到区块
	/mine				去挖新的区块
	/chain				返回区块链
	'''
	
# 实例化一个节点
app = Flask(__name__)

# 为节点生成一个128位的全局唯一标识符,删去-
node_identifier = str(uuid4()).replace('-','')

# 实例化一个区块链
blockchain = Blockchain()

'''
挖矿
	1.计算工作量证明PoW
	2.新增交易得到一个coin
	3.构造新的block添加到链中
'''
@app.route('/mine', methods=['GET'])
def mine():
	last_block = blockchain.last_block	#得到上一个block的proof
	last_proof = last_block['proof']
	proof = blockchain.proof_of_work(last_proof)

	#给算出proof的节点提供奖励，发送0表明挖出新币
	blockchain.new_transaction(
		sender = '0',
		recipient = node_identifier,
		amount = 1
		)
	#将新块添加到区块链上
	block = blockchain.new_block(proof, None)
	
	response = {
		'message': '新的block被添加',
		'index': block['index'],
		'transactions': block['transactions'],
		'proof': block['proof'],
		'previous_hash': block['previous_hash']
	}
	return jsonify(response), 200

#接收发送的交易的POST请求
'''
得到的数据结构
{
	"sender": "my address",
	"recipient": "someone",
	"amount": 5
}
'''
@app.route('/transactions/new', methods=['POST'])
def new_transaction():
	values = request.get_json()
	#对接收到的信息判断录入区块链表中
	required = ['sender', 'recipient', 'amount']
	if not all(k in values for k in required):	#如果接受的信息和需要的不匹配
		return '丢失信息',400

	index = blockchain.new_transaction(values['sender'],values['recipient'],values['amount'])

	response = {'message':'Transaction will be added to Block '+str(index)}
	return jsonify(response),201


@app.route('/chain', methods=['GET'])
def full_chain():
	response = {
		'chain': blockchain.chain,
		'length': len(blockchain.chain)
	}
	return jsonify(response), 200

# 注册节点
@app.route('/nodes/register', methods=['POST'])
def register_nodes():
	values = request.get_json()
	# 检查节点是否有效
	nodes = values.get('nodes')
	if nodes is None:
		return "Error: 请提交有效的节点列表", 400
	# 注册节点
	for node in nodes:
		blockchain.register_node(node)

	response = {
		'message': 'New nodes have been added',
		'total_nodes': list(blockchain.nodes),
	}
	return jsonify(response), 201
	

#解决冲突
@app.route('/nodes/resolve', methods=['GET'])
def consensus():
	replaced = blockchain.resolve_conflicts()

	if replaced:
		response = {
			'message': 'Our chain was replaced',
			'new_chain': blockchain.chain
		}
	else:
		response = {
			'message': 'Our chain is authoritative',
			'chain': blockchain.chain
		}

	return jsonify(response), 200

if __name__ == '__main__':

	parser = ArgumentParser()
	parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
	args = parser.parse_args()
	port = args.port

	app.run(host='127.0.0.1', port=port)
