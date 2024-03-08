import base64
import json
import time
import sys
from curl_cffi.requests import AsyncSession
import asyncio
from loguru import logger
from eth_account.messages import encode_defunct
from web3 import AsyncWeb3

logger.remove()
logger.add(sys.stdout, colorize=True, format="<g>{time:HH:mm:ss:SSS}</g> | <c>{level}</c> | <level>{message}</level>")

if sys.platform == "win32" and sys.version_info >= (3, 8):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class every_task:
  def __init__(self, private_key):
    headers = {
        "Referer": "https://pilot.ultiverse.io/",
        "Origin": "https://pilot.ultiverse.io",
        "Ul-Auth-Api-Key": "YWktYWdlbnRAZFd4MGFYWmxjbk5s",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    self.http = AsyncSession(timeout=120, headers=headers, impersonate="chrome120")
    self.web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider('https://opbnb-rpc.publicnode.com'))
    self.account = self.web3.eth.account.from_key(private_key)
    self.http.headers.update({"Ul-Auth-Address": self.account.address})
    abi = [
        {
          "inputs": [
              {
                  "internalType": "uint256",
                  "name": "deadline",
                  "type": "uint256"
              },
              {
                  "internalType": "uint256",
                  "name": "voyageId",
                  "type": "uint256"
              },
              {
                  "internalType": "uint16[]",
                  "name": "destinations",
                  "type": "uint16[]"
              },
              {
                  "internalType": "bytes32",
                  "name": "data",
                  "type": "bytes32"
              },
              {
                  "internalType": "bytes",
                  "name": "signature",
                  "type": "bytes"
              }
          ],
          "name": "explore",
          "outputs": [],
          "stateMutability": "nonpayable",
          "type": "function"
      },
    ]
    self.contract_address = self.web3.to_checksum_address('0x16d4c4b440cb779a39b0d8b89b1590a4faa0215d')
    self.contract = self.web3.eth.contract(address=self.contract_address, abi=abi)
    # abc = self.web3.eth.contract("0x16d4c4b440cb779a39b0d8b89b1590a4faa0215d")
    # signature = await self.get_nonce()

  # 请求签名
  async def get_nonce(self):
    try:
        json_data = {
            "address": self.account.address,
            "feature": "assets-wallet-login",
            "chainId": 204
        }
        res = await self.http.post('https://toolkit.ultiverse.io/api/user/signature', json=json_data)
        if 'success' in res.text and res.json()['success']:
            message = res.json()['data']['message']
            signature = self.account.sign_message(encode_defunct(text=message))
            return signature.signature.hex()
        logger.error(f'[{self.account.address}] 获取nonce失败：{res.text}')
        return None
    except Exception as e:
        logger.error(f'[{self.account.address}] 获取nonce异常：{e}')
        return None
  # 登录
  async def signin(self):
    try:
      signature = await self.get_nonce()
      if signature is None:
          return False
      json_data = {
          "address": self.account.address,
          "signature": signature,
          "chainId": 204
      }
      res = await self.http.post('https://toolkit.ultiverse.io/api/wallets/signin', json=json_data)
      if 'success' in res.text and res.json()['success']:
          access_token = res.json()['data']['access_token']
          self.http.headers.update({"Ul-Auth-Token": access_token})
          logger.success(f'[{self.account.address}] 登录成功')
          return True
      logger.error(f'[{self.account.address}] 登录失败：{res.text}')
      return False
    except Exception as e:
      logger.error(f'[{self.account.address}] 登录异常：{e}')
      return False
  
  # 获取用户任务
  async def get_task(self):
    try:
      res = await self.http.get('https://pml.ultiverse.io/api/explore/list')
      if 'success' in res.text and res.json()['success']:
          lists = res.json()['data']
          return lists
      logger.error(f'[{self.account.address}] 获取任务列表失败：{res.text}')
      return None
    except Exception as e:
      logger.error(f'[{self.account.address}] 获取任务列表异常：{e}')
      return None
  
  # 获取用户soul
  async def get_soul(self):
    try:
      res = await self.http.get('https://pml.ultiverse.io/api/profile')
      if 'success' in res.text and res.json()['success']:
          soul = res.json()['data']['soulInWallets']
          soulNumber = int(soul) / 1000000
          return soulNumber
      logger.error(f'[{self.account.address}] 获取用户soul失败：{res.text}')
      return None
    except Exception as e:
      logger.error(f'[{self.account.address}] 获取用户soul异常：{e}')
      return None
    

  # 计算可以做的任务并提交合约交易
  async def request_task(self,tasks,souls):
    try:
      nowUseSoul = 0
      nowTask = []
      canDoSoul = souls
      for item in tasks:
          if item['explored'] == False:
            nowUseSoul += item['soul']
            if nowUseSoul > canDoSoul:
              break
            nowTask.append(item['worldId'])
      logger.success(f'可做任务列表{nowTask}')
      if len(nowTask) > 0:
        contractInfo = await self.get_contract_info(worlds=nowTask)
        mintSBT = self.contract.functions.explore(int(contractInfo['deadline']),contractInfo['voyageId'],contractInfo['destinations'],contractInfo['data'],contractInfo['signature'])
        if mintSBT is None:
          return False
        nonce = await self.web3.eth.get_transaction_count(self.account.address)
        tx = await mintSBT.build_transaction({
            'from': self.account.address,
            'chainId': 204,
            'gas': 2000000,
            'nonce': nonce,
            'maxFeePerGas': 18,
            'maxPriorityFeePerGas': 2,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = await self.web3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = await self.web3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
          logger.success(f"Mint交易成功,等待广播完成进行任务检查 hash:{tx_hash.hex()}")
          await asyncio.sleep(10)
          await self.check_request(id=contractInfo['voyageId'])
          return True
        else:
          logger.error(f"[{self.account.address}] Mint交易 {tx_hash.hex()} 失败")
          logger.error(f"[{self.account.address}] 失败原因 {receipt}")
        return None
      else:
        logger.error(f"可做任务为0，进行下一个")
        return None
    except Exception as e:
        logger.error(f"[{self.account.address}] Mint交易异常：{e}")
        return False
  
  # 传需要做的任务 请求合约数据
  async def get_contract_info(self,worlds):
    json_data = {
       "chainId":204,
       "worldIds":worlds
    }
    try:
      res = await self.http.post('https://pml.ultiverse.io/api/explore/sign',json=json_data)
      if 'success' in res.text and res.json()['success']:
          info = res.json()['data']
          return info
      logger.error(f'[{self.account.address}] 请求合约数据失败：{res.text}')
      return None
    except Exception as e:
      logger.error(f'[{self.account.address}] 请求合约数据异常：{e}')
      return None

  # 最后一步等待合约交易检查任务
  async def check_request(self,id):
    try:
        json_data = {
            "chainId": 204,
            "id":id
        }
        res = await self.http.get('https://pml.ultiverse.io/api/explore/check',params=json_data)
        if 'success' in res.text and res.json()['success']:
          logger.success(f'任务检查完成')
          return True
        else:
          logger.error(f'[{self.account.address}] 获取合约交易任务检查失败，三十秒后重新检查：{res.text}')
          await asyncio.sleep(30)
          await self.check_request(id=id)
        return None
    except Exception as e:
        logger.error(f'[{self.account.address}] 获取合约交易任务检查异常：{e}')
        return None
  



  
  # 做任务主类
  async def do_task(self):
    await self.signin()
    time.sleep(5)
    tasks = await self.get_task()
    logger.success(f'任务列表获取')
    time.sleep(5)
    souls = await self.get_soul()
    logger.success(f'用户当前剩余soul{souls}')
    await self.request_task(tasks=tasks,souls=souls)
    return None


async def main():
  with open('privateKey.txt', 'r') as file:
    lines = file.readline()
    while lines:
      line = lines.strip()
      DY = every_task(line)
      await DY.do_task()
      logger.success(f'任务完成等待两秒切换至下一个地址')
      await asyncio.sleep(2)
      lines = file.readline()
asyncio.run(main())
