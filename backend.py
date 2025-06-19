from WindPy import w
import time
import threading
import json
import asyncio
import websockets
import traceback
from collections import deque  # 使用高效的双端队列

# 配置参数
MAX_HISTORY_LENGTH = 10000  # 每个合约存储的最大数据点数
SEND_HISTORY_LENGTH = 300   # 每次发送给客户端的数据点数
SAVE_TO_FILE = False        # 是否保存数据到文件
SAVE_INTERVAL = 60          # 保存间隔(秒)

# 基础品种代码
symbols = {
    "IH": {"spot": "000016.SH"},
    "IF": {"spot": "000300.SH"},
    "IC": {"spot": "000905.SH"},
    "IM": {"spot": "000852.SH"},
}

# 合约后缀
contract_suffix = ".CFE"

# 合约月份编号
contract_month_codes = ["00", "01", "02", "03"]

# 生成期货合约代码列表
def generate_future_contracts(symbol):
    return [f"{symbol}{m}{contract_suffix}" for m in contract_month_codes]

# 初始化缓存结构
data_cache = {}
real_time_data = {}
last_sent_data = {}  # 记录上次发送的数据位置

for sym in symbols:
    data_cache[sym] = {}
    real_time_data[sym] = {}
    future_contracts = generate_future_contracts(sym)
    for fc in future_contracts:
        data_cache[sym][fc] = {
            "future_price": None,
            "future_time": None,
            "spot_price": None,
            "spot_time": None,
        }
        # 使用deque替代列表，设置最大长度
        real_time_data[sym][fc] = deque(maxlen=MAX_HISTORY_LENGTH)
        last_sent_data[fc] = 0  # 初始化发送位置

# 现货代码缓存
spot_codes = {sym: symbols[sym]["spot"] for sym in symbols}

# 订阅字段
future_fields = ["rt_latest", "rt_time"]
spot_fields = ["rt_latest", "rt_time"]

# 反向映射
code_to_symbol_contract = {}
for sym in symbols:
    spot_code = symbols[sym]["spot"]
    code_to_symbol_contract[spot_code] = (sym, "spot")
    for fc in generate_future_contracts(sym):
        code_to_symbol_contract[fc] = (sym, fc)

def parse_rt_time(rt_time):
    try:
        rt_time_str = f"{int(rt_time):06d}"
        return f"{rt_time_str[0:2]}:{rt_time_str[2:4]}:{rt_time_str[4:6]}"
    except:
        return "00:00:00"

def on_wind_data(indata):
    try:
        # print(f"\n[Wind数据原始输入] Code: {indata.Codes[0]}, Fields: {indata.Fields}, Data: {indata.Data}")  # 调试输出
        code = indata.Codes[0]
        fields = indata.Fields
        data = indata.Data

        if code not in code_to_symbol_contract:
            return

        sym, contract_or_spot = code_to_symbol_contract[code]
        timestamp = time.time()  # 统一时间戳

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
        if contract_or_spot == "spot":
            return
            
        d = data_cache[sym][contract_or_spot]
        if d["future_price"] is not None and d["spot_price"] is not None:
            basis = round(d["future_price"] - d["spot_price"], 2)
            time_str = d["future_time"] or d["spot_time"] or time.strftime("%H:%M:%S")
            
            # 使用高效的方式添加数据
            real_time_data[sym][contract_or_spot].append({
                "time": time_str, 
                "basis": basis,
                "timestamp": timestamp
            })

            # 调试输出
            if len(real_time_data[sym][contract_or_spot]) % 100 == 0:
                print(f"[{time_str}] {sym} {contract_or_spot} Basis: {basis} | "
                      f"Data points: {len(real_time_data[sym][contract_or_spot])}")
                
            # print(f"[DEBUG] 新增数据点: {sym} {contract_or_spot} -> {basis}")


    except Exception as e:
        print("Wind数据异常：", e)
        traceback.print_exc()

# 数据保存函数
def save_data_periodically():
    while True:
        time.sleep(SAVE_INTERVAL)
        if not SAVE_TO_FILE:
            continue
            
        try:
            timestamp = int(time.time())
            filename = f"basis_data_{timestamp}.json"
            with open(filename, 'w') as f:
                # 只保存需要的数据
                save_data = {}
                for sym in real_time_data:
                    save_data[sym] = {}
                    for contract, data in real_time_data[sym].items():
                        save_data[sym][contract] = list(data)
                json.dump(save_data, f)
            print(f"数据已保存到 {filename}")
        except Exception as e:
            print("保存数据时出错:", e)

def start_wind():
    w.start()
    # print("WindPy连接成功，版本:", w.wssq("000001.SH").Data[0][0])
    print("WindPy连接成功")

    # # 订阅所有合约
    # all_codes = []
    # for sym in symbols:
    #     future_contracts = generate_future_contracts(sym)
    #     all_codes.extend(future_contracts)
    #     all_codes.append(symbols[sym]["spot"])
    
    # # 批量订阅，减少请求次数
    # fields = list(set(future_fields + spot_fields))  # 去重
    # w.wsq(",".join(all_codes), ",".join(fields), func=on_wind_data)
    # print(f"已订阅 {len(all_codes)} 个合约")

    # 重新设计订阅方式
    all_codes = []
    # 期货合约订阅（必须包含两个字段）
    for sym in symbols:
        futures = generate_future_contracts(sym)
        for fc in futures:
            w.wsq(fc, "rt_latest,rt_time", func=on_wind_data)  # 显式指定两个字段
            all_codes.append(fc)
    
    # 现货合约订阅（单独处理）
    for sym in symbols:
        spot = symbols[sym]["spot"]
        w.wsq(spot, "rt_latest,rt_time", func=on_wind_data)
        all_codes.append(spot)

    # 启动数据保存线程
    if SAVE_TO_FILE:
        threading.Thread(target=save_data_periodically, daemon=True).start()

    while True:
        time.sleep(1)

async def send_data(websocket, path):
    try:
        print(f"客户端连接: {websocket.remote_address}")
        # # ✅ 发送所有合约的最近 SEND_HISTORY_LENGTH 条数据（仅连接建立时发送一次）
        # send_obj = {}
        # for sym in real_time_data:
        #     for contract_code, data_deque in real_time_data[sym].items():
        #         # 获取最近 SEND_HISTORY_LENGTH 条数据
        #         new_data = list(data_deque)[-SEND_HISTORY_LENGTH:]
        #         if new_data:
        #             send_obj[contract_code] = new_data
        #         # ✅ 不再重置 last_sent_data，保持为默认 0 或原值，避免误认为已发送
        #         # last_sent_data[contract_code] = len(data_deque) ← 注释掉这行
        
        # ✅ 发送所有合约当天的数据
        send_obj = {}
        start_of_day = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))  # 今天0点的时间戳

        for sym in real_time_data:
            for contract_code, data_deque in real_time_data[sym].items():
                # 过滤出当天的数据
                new_data = [item for item in data_deque if item["timestamp"] >= start_of_day]
                if new_data:
                    send_obj[contract_code] = new_data
                # ✅ 不要修改 last_sent_data[contract_code]，否则会跳过新增数据

        # 发送历史数据给前端
        if send_obj:
            await websocket.send(json.dumps(send_obj, ensure_ascii=False))

        # ✅ 持续发送增量数据
        while True:
            # 仅发送自上次更新后的新数据
            send_obj = {}
            for sym in real_time_data:
                for contract_code, data_deque in real_time_data[sym].items():
                    # 获取新数据点
                    last_index = last_sent_data[contract_code]
                    current_length = len(data_deque)
                    
                    if current_length > last_index:
                        # 获取新增数据点，最多SEND_HISTORY_LENGTH个
                        new_data = list(data_deque)[last_index:]
                        if len(new_data) > SEND_HISTORY_LENGTH:
                            new_data = new_data[-SEND_HISTORY_LENGTH:]
                        
                        send_obj[contract_code] = new_data
                        last_sent_data[contract_code] = current_length
            
            if send_obj:
                await websocket.send(json.dumps(send_obj, ensure_ascii=False))
            
            await asyncio.sleep(0.5)  # 更频繁的更新
    except websockets.exceptions.ConnectionClosed:
        print(f"客户端断开: {websocket.remote_address}")
    except Exception as e:
        print("WebSocket异常:", e)

async def main():
    server = await websockets.serve(send_data, "localhost", 8765)
    print("WebSocket server started at ws://localhost:8765")
    await server.wait_closed()

if __name__ == '__main__':
    threading.Thread(target=start_wind, daemon=True).start()
    asyncio.run(main())