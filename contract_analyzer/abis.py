# Minimal ABIs to avoid external fetch when unverified.

ERC20_MINIMAL_ABI = [
  {"type":"function","name":"decimals","inputs":[],"outputs":[{"type":"uint8"}],"stateMutability":"view"},
  {"type":"function","name":"symbol","inputs":[],"outputs":[{"type":"string"}],"stateMutability":"view"},
  {"type":"function","name":"name","inputs":[],"outputs":[{"type":"string"}],"stateMutability":"view"},
  {"type":"function","name":"totalSupply","inputs":[],"outputs":[{"type":"uint256"}],"stateMutability":"view"},
  {"type":"function","name":"balanceOf","inputs":[{"name":"a","type":"address"}],"outputs":[{"type":"uint256"}],"stateMutability":"view"},
  {"type":"function","name":"transfer","inputs":[{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"type":"bool"}],"stateMutability":"nonpayable"},
  {"type":"function","name":"allowance","inputs":[{"type":"address","name":"o"},{"type":"address","name":"s"}],"outputs":[{"type":"uint256"}],"stateMutability":"view"},
  {"type":"function","name":"approve","inputs":[{"type":"address","name":"s"},{"type":"uint256","name":"v"}],"outputs":[{"type":"bool"}],"stateMutability":"nonpayable"}
]

# Ownable/AccessControl (partial) to probe when present
OWNABLE_ABI = [{"type":"function","name":"owner","inputs":[],"outputs":[{"type":"address"}],"stateMutability":"view"}]
ACCESS_CONTROL_ABI = [
  {"type":"function","name":"hasRole","inputs":[{"type":"bytes32","name":"role"},{"type":"address","name":"account"}],"outputs":[{"type":"bool"}],"stateMutability":"view"},
  {"type":"function","name":"getRoleAdmin","inputs":[{"type":"bytes32","name":"role"}],"outputs":[{"type":"bytes32"}],"stateMutability":"view"},
  {"type":"function","name":"getRoleMember","inputs":[{"type":"bytes32","name":"role"},{"type":"uint256","name":"index"}],"outputs":[{"type":"address"}],"stateMutability":"view"},
  {"type":"function","name":"getRoleMemberCount","inputs":[{"type":"bytes32","name":"role"}],"outputs":[{"type":"uint256"}],"stateMutability":"view"}
]

PAUSABLE_ABI = [{"type":"function","name":"paused","inputs":[],"outputs":[{"type":"bool"}],"stateMutability":"view"}]

UNIV2_FACTORY_ABI = [
  {"type":"function","name":"getPair","inputs":[{"type":"address","name":"tokenA"},{"type":"address","name":"tokenB"}],"outputs":[{"type":"address"}],"stateMutability":"view"}
]
UNIV2_PAIR_ABI = [
  {"type":"function","name":"getReserves","inputs":[],"outputs":[
    {"type":"uint112","name":"_reserve0"},{"type":"uint112","name":"_reserve1"},{"type":"uint32","name":"_blockTimestampLast"}],"stateMutability":"view"},
  {"type":"function","name":"token0","inputs":[],"outputs":[{"type":"address"}],"stateMutability":"view"},
  {"type":"function","name":"token1","inputs":[],"outputs":[{"type":"address"}],"stateMutability":"view"},
  {"type":"function","name":"totalSupply","inputs":[],"outputs":[{"type":"uint256"}],"stateMutability":"view"},
  {"type":"function","name":"balanceOf","inputs":[{"type":"address","name":"a"}],"outputs":[{"type":"uint256"}],"stateMutability":"view"}
]

# Uniswap v3 Position Manager (partial)
UNIV3_NPM_ABI = [
  {"type":"function","name":"positions","inputs":[{"type":"uint256","name":"tokenId"}],
   "outputs":[
     {"type":"uint96","name":"nonce"},{"type":"address","name":"operator"},{"type":"address","name":"token0"},{"type":"address","name":"token1"},
     {"type":"uint24","name":"fee"},{"type":"int24","name":"tickLower"},{"type":"int24","name":"tickUpper"},{"type":"uint128","name":"liquidity"},
     {"type":"uint256","name":"feeGrowthInside0LastX128"},{"type":"uint256","name":"feeGrowthInside1LastX128"},{"type":"uint128","name":"tokensOwed0"},
     {"type":"uint128","name":"tokensOwed1"}],"stateMutability":"view"}
]
