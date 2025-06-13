from WindPy import w
import time
import threading
import json
import asyncio
import websockets
import traceback

# 基础品种代码
symbols = {
    "IH": {"spot": "000016.SH"},
    "IF": {"spot": "000300.SH"},
    "IC": {"spot": "000905.SH"},
    "IM": {"spot": "000852.SH"},
}

# 合约后缀
contract_suffix = ".CFE"

# 合约月份编号：当月=00，次月=01，当季=02，次季=03（示例）
contract_month_codes = ["00", "01", "02", "03"]

# 生成期货合约代码列表，比如IC00.CFE, IC01.CFE ...
def generate_future_contracts(symbol):
    return [f"{symbol}{m}{contract_suffix}" for m in contract_month_codes]

# 初始化缓存结构
data_cache = {}
real_time_data = {}

for sym in symbols:
    # 期货合约缓存，按合约存
    data_cache[sym] = {}
    real_time_data[sym] = {}
    future_contracts = generate_future_contracts(sym)
    for fc in future_contracts:
        data_cache[sym][fc] = {
            "future_price": None,
            "future_time": None,
            "spot_price": None,   # 现货是共享的，后面更新时复制
            "spot_time": None,
        }
        real_time_data[sym][fc] = []

# 现货代码缓存（只订阅一次）
spot_codes = {sym: symbols[sym]["spot"] for sym in symbols}

# 订阅字段
future_fields = ["rt_latest", "rt_time"]
spot_fields = ["rt_latest", "rt_time"]

# 反向映射code => (symbol, future_contract or 'spot')
code_to_symbol_contract = {}
for sym in symbols:
    # 现货
    spot_code = symbols[sym]["spot"]
    code_to_symbol_contract[spot_code] = (sym, "spot")
    # 多合约期货
    for fc in generate_future_contracts(sym):
        code_to_symbol_contract[fc] = (sym, fc)

def parse_rt_time(rt_time):
    try:
        rt_time_str = f"{int(rt_time):06d}"
        hour = rt_time_str[0:2]
        minute = rt_time_str[2:4]
        second = rt_time_str[4:6]
        return f"{hour}:{minute}:{second}"
    except:
        return "00:00:00"

def on_wind_data(indata):
    try:
        code = indata.Codes[0]
        fields = indata.Fields
        data = indata.Data

        if code not in code_to_symbol_contract:
            return

        sym, contract_or_spot = code_to_symbol_contract[code]

        # 更新缓存
        if contract_or_spot == "spot":
            # 更新所有期货合约的现货价
            for fc in data_cache[sym]:
                for i, field in enumerate(fields):
                    value = data[i][0]
                    if field.upper() == "RT_LATEST":
                        data_cache[sym][fc]["spot_price"] = round(value, 2)
                    elif field.upper() == "RT_TIME":
                        data_cache[sym][fc]["spot_time"] = parse_rt_time(value)
        else:
            # 期货合约更新
            for i, field in enumerate(fields):
                value = data[i][0]
                if field.upper() == "RT_LATEST":
                    data_cache[sym][contract_or_spot]["future_price"] = round(value, 2)
                elif field.upper() == "RT_TIME":
                    data_cache[sym][contract_or_spot]["future_time"] = parse_rt_time(value)

        # 计算基差，存储
        d = None
        if contract_or_spot == "spot":
            # 现货数据不单独计算
            return
        else:
            d = data_cache[sym][contract_or_spot]

        if d["future_price"] is not None and d["spot_price"] is not None:
            basis = round(d["future_price"] - d["spot_price"], 2)
            time_str = d["future_time"] or d["spot_time"] or time.strftime("%H:%M:%S")

            print(f"[{time_str}] {sym} {contract_or_spot} Future: {d['future_price']}, Spot: {d['spot_price']}, Basis: {basis}")

            real_time_data[sym][contract_or_spot].append({"time": time_str, "basis": basis})
            if len(real_time_data[sym][contract_or_spot]) > 300:
                real_time_data[sym][contract_or_spot].pop(0)

    except Exception as e:
        print("Wind数据异常：", e)
        traceback.print_exc()

def start_wind():
    w.start()

    # 订阅所有期货合约
    for sym in symbols:
        future_contracts = generate_future_contracts(sym)
        for fc in future_contracts:
            w.wsq(fc, ",".join(future_fields), func=on_wind_data)
        # 订阅现货代码
        w.wsq(symbols[sym]["spot"], ",".join(spot_fields), func=on_wind_data)

    while True:
        time.sleep(1)

async def send_data(websocket, path):
    try:
        while True:
            # 扁平化 real_time_data，key为合约代码，方便前端处理
            send_obj = {}
            for sym in real_time_data:
                for contract_code, data_list in real_time_data[sym].items():
                    send_obj[contract_code] = data_list

            await websocket.send(json.dumps(send_obj, ensure_ascii=False))
            await asyncio.sleep(1)
    except websockets.exceptions.ConnectionClosed:
        print("客户端断开连接")

async def main():
    server = await websockets.serve(send_data, "localhost", 8765)
    print("WebSocket server started at ws://localhost:8765")
    await server.wait_closed()

if __name__ == '__main__':
    threading.Thread(target=start_wind, daemon=True).start()
    asyncio.run(main())
