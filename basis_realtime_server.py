from WindPy import w
import time
import threading
import json
import asyncio
import websockets
import traceback

# 配置你要监控的品种及对应期货和现货代码
symbols = {
    "IH": {"future": "IH.CFE", "spot": "000016.SH"},
    "IF": {"future": "IF.CFE", "spot": "000300.SH"},
    "IC": {"future": "IC.CFE", "spot": "000905.SH"},
    "IM": {"future": "IM.CFE", "spot": "000852.SH"},
}

# 订阅字段
future_fields = ["rt_latest", "rt_time"]
spot_fields = ["rt_latest", "rt_time"]

# 各品种数据缓存结构初始化
data_cache = {
    sym: {
        "future_price": None,
        "future_time": None,
        "spot_price": None,
        "spot_time": None,
    } for sym in symbols
}

real_time_data = {
    sym: [] for sym in symbols
}

# 时间格式转换
def parse_rt_time(rt_time):
    try:
        rt_time_str = f"{int(rt_time):06d}"
        hour = rt_time_str[0:2]
        minute = rt_time_str[2:4]
        second = rt_time_str[4:6]
        return f"{hour}:{minute}:{second}"
    except Exception as e:
        return "00:00:00"

# 反向映射 code 到 symbol 和类型（期货/现货），方便回调处理
code_to_symbol = {}
for sym, codes in symbols.items():
    code_to_symbol[codes["future"]] = (sym, "future")
    code_to_symbol[codes["spot"]] = (sym, "spot")

# Wind统一回调函数
def on_wind_data(indata):
    try:
        code = indata.Codes[0]
        fields = indata.Fields
        data = indata.Data

        if code not in code_to_symbol:
            return  # 非关注代码数据忽略

        sym, typ = code_to_symbol[code]

        # 逐字段更新缓存
        for i, field in enumerate(fields):
            value = data[i][0]
            if typ == "future":
                if field.upper() == "RT_LATEST":
                    data_cache[sym]["future_price"] = round(value, 2)
                elif field.upper() == "RT_TIME":
                    data_cache[sym]["future_time"] = parse_rt_time(value)
            elif typ == "spot":
                if field.upper() == "RT_LATEST":
                    data_cache[sym]["spot_price"] = round(value, 2)
                elif field.upper() == "RT_TIME":
                    data_cache[sym]["spot_time"] = parse_rt_time(value)

        # 计算基差并存储
        d = data_cache[sym]
        if d["future_price"] is not None and d["spot_price"] is not None:
            basis = round(d["future_price"] - d["spot_price"], 2)
            time_str = d["future_time"] or d["spot_time"] or time.strftime("%H:%M:%S")

            print(f"[{time_str}] {sym} Future: {d['future_price']}, Spot: {d['spot_price']}, Basis: {basis}")

            real_time_data[sym].append({"time": time_str, "basis": basis})
            if len(real_time_data[sym]) > 300:
                real_time_data[sym].pop(0)

    except Exception as e:
        print("Wind数据异常：", e)
        traceback.print_exc()

# 启动Wind订阅
def start_wind():
    w.start()

    # 订阅所有期货代码
    for sym in symbols:
        w.wsq(symbols[sym]["future"], ",".join(future_fields), func=on_wind_data)
        w.wsq(symbols[sym]["spot"], ",".join(spot_fields), func=on_wind_data)

    while True:
        time.sleep(1)

# WebSocket推送
async def send_data(websocket, path):
    try:
        while True:
            await websocket.send(json.dumps(real_time_data, ensure_ascii=False))
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
