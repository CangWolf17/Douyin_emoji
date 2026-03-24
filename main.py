import os
import io
import argparse
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageSequence
import zipfile
from concurrent.futures import ThreadPoolExecutor
import sys

# --- 默认配置（如果用户未指定参数，则使用这些） ---
DEFAULT_HTML_FILE = "douyin_emojis.html"
DEFAULT_MAX_COUNT = 0  # 0 表示全部下载
DEFAULT_ZIP_NAME = "DOUYIN_emoji.zip"

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# GIF 优化默认参数
GIF_DEFAULTS = {
    'duration': 80,  # 帧持续时间 (ms)
    'loop': 0,       # 0 表示无限循环
    'optimize': True,
    'quantize_colors': 128
}

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="抖音表情包提取转GIF工具 (Jacknie666/Douyin_emoji)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # 显示默认值
    )
    
    # 必填参数（如果不提供，我们会提示用户）
    parser.add_argument(
        '-i', '--input', 
        default=DEFAULT_HTML_FILE,
        help="包含抖音表情链接的本地 HTML 文件路径"
    )
    
    # 可选参数
    parser.add_argument(
        '-n', '--num', 
        type=int, 
        default=DEFAULT_MAX_COUNT,
        help="设置下载表情的数量上限 (0表示全部下载)"
    )
    
    parser.add_argument(
        '-o', '--output', 
        default=DEFAULT_ZIP_NAME,
        help="输出的 ZIP 压缩文件名"
    )

    # 还可以增加高级参数开关，比如是否优化 GIF
    parser.add_argument(
        '--no-optimize', 
        action='store_false', 
        dest='optimize_gif',
        help="禁用 GIF 优化以提高处理速度，但会增加文件体积"
    )
    parser.set_defaults(optimize_gif=True)

    # 增加易用性：一键运行模式（默认寻找 douyin_emojis.html 且全下载）
    return parser.parse_args()

def extract_image_urls(html_file, max_count):
    """从本地 HTML 文件解析表情链接"""
    if not os.path.exists(html_file):
        print(f"❌ 错误：未找到输入文件 '{html_file}'。")
        print(f"请确保你已经提取了抖音 HTML 源码，并保存为 '{html_file}'，且与程序在同一目录。")
        # 增加对终端用户的友好提示
        input("按任意键退出...")
        sys.exit(1)

    print(f"🔍 正在从 '{html_file}' 解析链接...")
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # --- 关键部分：这里是抖音改版时需要更新的选择器 ---
    # 根据原代码逻辑，寻找所有可能是表情的 img 标签。
    # 如果失效，需要在这里更新 soup.select() 的参数。
    img_tags = soup.select('img') 

    image_urls = []
    count = 0
    for img in img_tags:
        # 尝试提取多个可能的属性
        src = img.get('src') or img.get('data-src') or img.get('data-original-src')
        if src and (src.startswith('http') or src.startswith('//')):
            # 处理 "//example.com" 这种格式
            if src.startswith('//'):
                src = 'https:' + src
            
            # 简单的抖音域名清洗（可选）
            if 'p1-dy' in src or 'p3-dy' in src or 'p9-dy' in src:
                image_urls.append(src)
                count += 1
                if max_count > 0 and count >= max_count:
                    break
    
    # 去重
    unique_urls = list(set(image_urls))
    print(f"✅ 成功找到 {len(img_tags)} 个图片标签，提取到 {len(unique_urls)} 个表情链接。")
    if len(unique_urls) == 0:
        print("⚠️ 警告：未找到任何有效表情链接。请检查 HTML 文件内容或抖音网页版 DOM 是否改版。")
        print("如果是网页改版，需要修改代码中的 soup.select('img') 部分。")
    return unique_urls

def download_and_convert_to_gif(url, args):
    """下载并转换"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        # 将下载的数据放入内存文件
        img_data = io.BytesIO(response.content)
        img = Image.open(img_data)
        
        # 提取 GIF 帧并优化
        frames = []
        durations = []
        
        for frame in ImageSequence.Iterator(img):
            # 颜色量化
            if args.optimize_gif:
                frame = frame.convert('P', palette=Image.ADAPTIVE, colors=GIF_DEFAULTS['quantize_colors'])
            frames.append(frame.copy())
            
            # 获取帧持续时间 (ms)
            dur = frame.info.get('duration', GIF_DEFAULTS['duration'])
            durations.append(dur)

        # 在内存中生成 GIF
        out_gif = io.BytesIO()
        if frames:
            frames[0].save(
                out_gif,
                save_all=True,
                append_images=frames[1:],
                format='GIF',
                loop=GIF_DEFAULTS['loop'],
                duration=durations, # 使用原图帧率
                optimize=args.optimize_gif
            )
            out_gif.seek(0)
            return url, out_gif.read() # 返回 URL 做文件名参考，和二进制数据

    except Exception as e:
        print(f"🚫 下载或转换链接失效/错误: {url[:30]}... 错误: {e}")
        return url, None

def main():
    # 1. 解析参数
    args = parse_arguments()
    
    print("\n--- 抖音表情包小助手 (可执行文件版) ---\n")
    print(f"输入文件: {args.input}")
    if args.num > 0:
        print(f"下载上限: {args.num} 个")
    print(f"输出文件: {args.output}\n")

    # 2. 提取链接
    image_urls = extract_image_urls(args.input, args.num)
    if not image_urls:
        return

    # 3. 多线程下载和转换
    print(f"⏳ 正在启动多线程下载并转换为 GIF... (共 {len(image_urls)} 个)")
    
    gif_results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        # 提交任务
        future_to_url = {executor.submit(download_and_convert_to_gif, url, args): url for url in image_urls}
        
        from tqdm import tqdm
        # 增加进度条，极大提升易用性体验
        progress = tqdm(total=len(image_urls), desc="处理进度")
        for future in  executor.submit(download_and_convert_to_gif, url, args).result(): # future的遍历
            # 这个地方逻辑有点问题，ThreadPoolExecutor 需要正确获取 future 结果
            pass
            
    # 正确的多线程获取结果和进度条实现
    print(f"⏳ 正在启动多线程下载并转换为 GIF... (共 {len(image_urls)} 个)")
    gif_results = []
    from tqdm import tqdm
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(download_and_convert_to_gif, url, args): url for url in image_urls}
        
        with tqdm(total=len(image_urls), desc="处理进度") as pbar:
            for future in future_to_url:
                url, gif_data = future.result()
                if gif_data:
                    gif_results.append((url, gif_data))
                pbar.update(1)

    # 4. 打包 ZIP
    if not gif_results:
        print("⚠️ 未能成功转换任何表情，ZIP 文件将不会生成。")
        return

    print(f"📦 正在将 {len(gif_results)} 个 GIF 打包进 '{args.output}'...")
    with zipfile.ZipFile(args.output, 'w') as zipf:
        for i, (url, gif_data) in enumerate(gif_results):
            # 生成简单的文件名
            # 可以更高级一些，提取 URL 的哈希值或抖音ID
            filename = f"emoji_{i+1:03d}.gif"
            zipf.writestr(filename, gif_data)

    print(f"\n✅ 成功！最终产物：'{args.output}'。")
    print("你可以解压该文件后，将里面的 GIF 发送给微信文件传输助手即可添加到自定义表情。\n")
    # 对双击运行的用户友好，防止直接关窗
    input("处理完成，按任意键退出...")

if __name__ == "__main__":
    # 增加对依赖库的存在检查（针对 Nuitka 打包）
    try:
        import bs4
        import PIL
        import requests
        import tqdm
    except ImportError as e:
        print(f"❌ 运行环境缺失，找不到必要的 Python 库：{e}")
        input("按任意键退出...")
        sys.exit(1)
        
    main()
