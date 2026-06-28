
import sys
import os
import time

# 尝试导入 steamworks
try:
    from steamworks.steamworks import STEAMWORKS
except ImportError:
    print("ERROR: steamworks-py not installed in the environment")
    sys.exit(1)

def main():
    if len(sys.argv) < 3:
        print("Usage: python steam_worker.py <action> <mod_id>")
        sys.exit(1)

    action = sys.argv[1]
    mod_id = int(sys.argv[2])

    print(f"Agent starting: {action} -> {mod_id}")

    # 初始化 Steamworks
    # 因为我们在 tools/steam_agent 目录下运行，它会自动读取当前目录的 DLL 和 appid.txt
    try:
        steam = STEAMWORKS()
        steam.initialize()
    except Exception as e:
        print(f"ERROR: Steam init failed: {e}")
        sys.exit(2)

    if not steam:
        print("ERROR: Steam API not loaded")
        sys.exit(2)

    # 定义回调
    def callback(res):
        print(f"Callback: {res}")

    success = False
    try:
        if action == "subscribe":
            steam.Workshop.SubscribeItem(mod_id, callback)
            success = True
            print("SUCCESS: Subscription request sent")
        elif action == "unsubscribe":
            steam.Workshop.UnsubscribeItem(mod_id, callback)
            success = True
            print("SUCCESS: Unsubscription request sent")
        else:
            print(f"ERROR: Unknown action {action}")
    except Exception as e:
        print(f"ERROR: Action failed: {e}")

    # 给 Steam 客户端一点时间处理请求
    if success:
        time.sleep(1)

if __name__ == "__main__":
    main()
