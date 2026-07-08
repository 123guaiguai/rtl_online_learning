import asyncio
import sys
import json
import urllib.request
from playwright.async_api import async_playwright

async def main():
    print("🚀 正在获取浏览器调试接口信息 (http://localhost:9333/json/version)...")
    try:
        req = urllib.request.Request(
            "http://localhost:9333/json/version", 
            headers={"Host": "localhost:9333"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            info = json.loads(response.read().decode())
            print(f"📋 浏览器版本信息: {info.get('Browser')}")
            ws_url = info.get('webSocketDebuggerUrl')
            print(f"🔗 WebSocket 调试 URL: {ws_url}")
    except Exception as e:
        print(f"❌ 无法连接到调试接口！")
        print("请确保：")
        print("1. 您的 Edge/Chrome 在启动时添加了 --remote-allow-origins=* 参数。")
        print("2. 启动命令如：& \"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe\" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=\"C:\\Users\\fifteen\\edge_debug_profile\"")
        print(f"详细错误: {e}")
        sys.exit(1)

    print("🚀 正在通过 Playwright 连接 CDP...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(ws_url)
            print("✅ 成功连接到本地 Chrome/Edge 实例！")
        except Exception as e:
            print(f"❌ Playwright CDP 连接失败: {e}")
            sys.exit(1)

        # 智能匹配：先寻找在您浏览器中已经打开的 5173 前端标签页
        page = None
        print("🔍 正在检索浏览器中已打开的页面...")
        for context in browser.contexts:
            for p_obj in context.pages:
                url = p_obj.url
                try:
                    title = await p_obj.title()
                except:
                    title = ""
                if "5173" in url or "rtl_tutor" in title.lower():
                    page = p_obj
                    print(f"🎯 找到已打开的前端标签页: '{title}' ({url})，直接接管该页面进行调试！")
                    break
            if page:
                break

        # 如果没找到，则新建一个页面并使用真实服务器 IP 访问
        if not page:
            print("💡 未找到已打开的标签页，正在新建页面...")
            context = browser.contexts[0]
            page = await context.new_page()
            target_url = "http://113.54.240.172:5173"
            print(f"👉 正在控制您的浏览器跳转到服务器真实 IP 地址: {target_url}...")
            try:
                await page.goto(target_url, timeout=15000)
                print("✨ 页面加载成功！")
            except Exception as e:
                print(f"⚠️ 页面跳转超时: {e}")

        # 开始自动点击 'Prob001 zero' 选项
        try:
            print("👉 正在自动点击列表中的 'Prob001 zero' 选项...")
            await page.click("text=Prob001 zero", timeout=5000)
            print("✨ 点击成功！您应该能在屏幕上看到题目已切换。")
        except Exception as e:
            print(f"⚠️ 自动点击失败 (请确保网页已完全加载且包含题目列表): {e}")
        
        await page.wait_for_timeout(3000)
        print("🎉 自动化控制测试结束！")

if __name__ == "__main__":
    asyncio.run(main())
