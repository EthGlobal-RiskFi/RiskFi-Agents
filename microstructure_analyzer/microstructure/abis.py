# Minimal ABIs used by the analyzer.
IUniswapV3Pool_ABI = [
  {"inputs":[],"name":"slot0","outputs":[
    {"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},
    {"internalType":"int24","name":"tick","type":"int24"},
    {"internalType":"uint16","name":"observationIndex","type":"uint16"},
    {"internalType":"uint16","name":"observationCardinality","type":"uint16"},
    {"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},
    {"internalType":"uint8","name":"feeProtocol","type":"uint8"},
    {"internalType":"bool","name":"unlocked","type":"bool"}
  ],"stateMutability":"view","type":"function"},
  {"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"},
  {"inputs":[],"name":"fee","outputs":[{"internalType":"uint24","name":"","type":"uint24"}],"stateMutability":"view","type":"function"},
  {"inputs":[],"name":"tickSpacing","outputs":[{"internalType":"int24","name":"","type":"int24"}],"stateMutability":"view","type":"function"},
  {"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
  {"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}
]

IERC20_MIN_ABI = [
  {"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
  {"constant":True,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},
  {"constant":True,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"}
]
