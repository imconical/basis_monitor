from WindPy import w
import time
import threading
import json
import asyncio
import websockets
import traceback

# 内存中缓存的最新数据
data_cache = {
    "future_price": None,
    "future_time": None,
    "spot_price": None,
    "spot_time": None,
}

real_time_data = []

future_code = "IC.CFE"
spot_code = "000905.SH"

# Wind字段
future_fields = ["rt_latest", "rt_time"]
spot_fields = ["rt_latest", "rt_time"]

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

# Wind统一回调函数
def on_wind_data(indata):
    global real_time_data

    try:
        code = indata.Codes[0]
        fields = indata.Fields
        data = indata.Data
        # print(f"Received data for code: {code}, fields: {fields}, data: {data}")
        # 逐字段更新缓存
        for i, field in enumerate(fields):
            value = data[i][0]
            if code == future_code:
                if field == "RT_LATEST":
                    data_cache["future_price"] = round(value,2)
                elif field == "RT_TIME":
                    data_cache["future_time"] = parse_rt_time(value)
            elif code == spot_code:
                if field == "RT_LATEST":
                    data_cache["spot_price"] = round(value,2)
                elif field == "RT_TIME":
                    data_cache["spot_time"] = parse_rt_time(value)

        # print(f"Updated data cache: {data_cache}")
        # 如果两边价格都齐了，可以计算基差
        if data_cache["future_price"] is not None and data_cache["spot_price"] is not None:
            basis = data_cache["future_price"] - data_cache["spot_price"]
            basis = round(basis, 2)
            time_str = data_cache["future_time"] or data_cache["spot_time"] or time.strftime("%H:%M:%S")

            print(f"[{time_str}] Future: {data_cache['future_price']}, Spot: {data_cache['spot_price']}, Basis: {basis}")

            real_time_data.append({"time": time_str, "basis": round(basis, 2)})
            if len(real_time_data) > 300:
                real_time_data.pop(0)

    except Exception as e:
        print("Wind数据异常：", e)
        traceback.print_exc()

# 启动Wind订阅
def start_wind():
    w.start()
    # 分别订阅期货和现货，注意回调函数是同一个
    w.wsq(future_code, ",".join(future_fields), func=on_wind_data)
    w.wsq(spot_code, ",".join(spot_fields), func=on_wind_data)

    while True:
        time.sleep(1)

# WebSocket推送
async def send_data(websocket, path):
    try:
        while True:
            await websocket.send(json.dumps(real_time_data))
            await asyncio.sleep(1)
    except websockets.exceptions.ConnectionClosed:
        print("客户端断开连接")

async def main():
    server = await websockets.serve(send_data, "localhost", 8765)
    print("WebSocket server started at ws://localhost:8765")
    await server.wait_closed()

if __name__ == '__main__':
    threading.Thread(target=start_wind).start()
    asyncio.run(main())
