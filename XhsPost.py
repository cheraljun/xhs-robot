import requests
import random
import json
import os
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
# 爬虫检测, 商业版用
# from kkrobots import Parse

class Config:
    # 可调：用户代理（UA）池，用于随机挑选伪装浏览器标识（可增删）
    user_agent_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    ]

    # 可调：滚动后用于懒加载的等待区间（毫秒），尽量小以小批量加载
    scroll_pause_ms_min = 300
    scroll_pause_ms_max = 450

    # 可调：模拟人类操作的随机等待区间（毫秒），影响整体节奏
    human_wait_ms_min = 1000
    human_wait_ms_max = 3000

    # 可调：贝塞尔曲线步数范围（步数越多移动越平滑但更慢）
    bezier_steps_min = 25
    bezier_steps_max = 45
    # 可调：第一控制点相对起点的随机偏移范围（像素）
    cp1_dx = (-120, 120)
    cp1_dy = (60, 180)
    # 可调：第二控制点相对终点的随机偏移范围（像素）
    cp2_dx = (-120, 120)
    cp2_dy = (-180, -60)
    # 可调：鼠标每一步移动之间的暂停区间（毫秒）
    per_step_pause_ms = (5, 18)

    # 可调：随机视口宽高范围（像素），用于伪装不同设备尺寸
    viewport_width = (1280, 1920)
    viewport_height = (720, 1080)

    # 可调：全局超时（毫秒），用于 Playwright 操作和页面加载
    timeout_value = 60000

    # 可调：目标地址
    explore_url = "https://www.xiaohongshu.com/explore"

    # 可调：页面选择器（不要改变值，仅集中配置）
    explore_container_selector = "#exploreFeeds"
    note_item_selector = ".note-item"
    title_selector = ".title"
    author_selector = ".name"  # 登录态使用 nth(0)
    like_count_selector = ".count"
    image_selector = "img"
    cover_selector = ".cover.mask.ld"
    comment_textarea_selector = "#content-textarea"
    close_selector = ".close.close-mask-dark"

    # 可调：详情页交互按钮选择器（关注/点赞/收藏）
    follow_button_selector = ".interaction-container .note-detail-follow-btn .reds-button-new-box"
    like_button_selector = ".interaction-container .interact-container .like-lottie"
    collect_button_selector = ".reds-icon.collect-icon"

    # 可调：评论模板（第二条评论从中随机选择一条，{love} 会被替换）
    comment_templates = [
        "{love}[红色心形R]好喜欢这条！顺手给博主点了个赞[棒R]～若你路过也来我主页随便看看[doge] 我把今日的心动收进“今日美学”，也许正好对你的口味。",
        "{love}[红色心形R]这份氛围太戳我了！给博主点个赞[棒R]～有缘的宝子路过可随意逛逛我的主页[doge] 我把灵感做成“今日美学”的小卡片，路过翻一页就好，说不定对你有用呢！",
        "{love}[红色心形R]看完心里软了一下～已为博主点赞[棒R]～我喜欢这种感觉，能看到这儿你品味一定很不错！来“今日美学”随便走走吧[doge] 我把这份心动先放在了小卡片里，等你来翻。"
    ]

    # 可调：Cookie（请替换为你自己的 web_session 值）
    cookie_web_session = "040069b90991b96487846a71e83a4b5cd14174"
    cookie_domain = ".xiaohongshu.com"
    cookie_path = "/"
    # 可调：鼠标滚轮每次滚动的像素距离范围（小步滚动）
    wheel_delta_min = 60
    wheel_delta_max = 180


class Storage:
    def __init__(self, json_path):
        self.json_path = json_path
        self._data = self._load()

    def _load(self):
        try:
            if not os.path.exists(self.json_path):
                with open(self.json_path, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
                return {}
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def contains(self, key):
        return key in self._data

    def add(self, key, record):
        self._data[key] = record
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"写入 {self.json_path} 失败: {e}")


class Humanizer:
    def __init__(self, config: Config):
        self.config = config
        self.mouse_x = None
        self.mouse_y = None

    def human_wait(self):
        wait = random.randint(self.config.human_wait_ms_min, self.config.human_wait_ms_max)
        print(f"模拟人类等待, 等待{wait/1000}秒")
        return wait

    def _bezier_point(self, p0, p1, p2, p3, t):
        return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * (t ** 2) * p2 + (t ** 3) * p3

    def move_mouse_bezier_to(self, page, locator):
        # 保留函数但不再用于定位点击（按你的要求改为纯选择器点击）
        try:
            _ = locator.count()  # 触发潜在错误以便捕获
            return None, None
        except Exception:
            return None, None


class Bottle:
    # 版权
    copyright = "YES!"

    # 初始化实例对象
    def __init__(self):
        # 欢迎
        self.welcome = f"\n欢迎使用由{Bottle.copyright}开发的小红书Post!\n"
        # 初始化滚动计数
        self.scroll_count = 0
        # 组件
        self.config = Config()
        self.humanizer = Humanizer(self.config)
        self.storage = Storage(os.path.join(os.path.dirname(__file__), "commented_notes.json"))
        
    # 模拟人类等待（兼容原API，委托到Humanizer）
    def human_wait(self):
        return self.humanizer.human_wait()
    # 情话api
    def loveword(self):
        try:
            result = requests.get(url = "https://api.pearktrue.cn/api/jdyl/qinghua.php").text
            return result
        except Exception as e:
            return None

    

    # 主函数Post
    def Post(self):
        # 欢迎
        print(self.welcome)
        # 启动playwright driver
        with sync_playwright() as driver:

            # 开启broswer
            browser = driver.chromium.launch(headless=False, timeout = self.config.timeout_value)

            # 创建浏览器上下文
            # 请求头与随机视口
            headers = {
                "user-agent": random.choice(self.config.user_agent_pool)  # 可调：从UA池随机挑选
            }
            cookies = [
                {"name": "web_session", "value": self.config.cookie_web_session,  # 可调：替换为你自己的有效Cookie
                 "domain": self.config.cookie_domain, 
                 "path": self.config.cookie_path}
            ]
            viewport = {
                "width": random.randint(*self.config.viewport_width),   # 可调：随机视口宽
                "height": random.randint(*self.config.viewport_height)  # 可调：随机视口高
            }
            context = browser.new_context(
                extra_http_headers=headers,
                viewport=viewport
            )
            context.add_cookies(cookies)

            print("正在打开浏览器")
            page = context.new_page()
            page.set_default_timeout(self.config.timeout_value)

            # 轮询等待工具：最多等待30秒；超时后人工介入，回车继续后重置计时
            def wait_until(locator_desc, locator_fn):
                print(f"等待元素出现：{locator_desc}")
                waited_ms = 0
                while True:
                    try:
                        el = locator_fn()
                        el.wait_for(state="visible", timeout=2000)
                        return el
                    except PlaywrightTimeoutError:
                        waited_ms += 2000
                        if waited_ms >= 30000:
                            print(f"等待 {locator_desc} 已达30秒，流程暂停。请手动处理页面后按回车继续...")
                            input()
                            waited_ms = 0  # 重置计时，继续等待
                        else:
                            page.wait_for_timeout(2000)
                    except Exception as e:
                        print(f"等待 {locator_desc} 时发生异常：{e}")
                        page.wait_for_timeout(2000)
                        continue

            # 导航至指定页面
            print("正在导航至小红书主页")
            page.goto(
                self.config.explore_url, 
                timeout = self.config.timeout_value
                )


            M = input("运行多少分钟? ")
            end_time = datetime.now() + timedelta(minutes = int(M))
            while datetime.now() < end_time:

                try:
                    # 获取探索页容器
                    explore_page = page.locator(self.config.explore_container_selector)

                    print(explore_page)
                    # 获取探索页所有笔记
                    note_items = explore_page.locator(self.config.note_item_selector)
                    
                    for i in range(note_items.count()):
                        item = note_items.nth(i)
                        # 标题
                        note_title = item.locator(self.config.title_selector).inner_text()
                        # 作者
                        note_author = item.locator(self.config.author_selector).nth(0).inner_text() # 登陆
                        '''
                        note_author = item.locator(".name").inner_text() #免登录
                        '''
                        # 喜欢数
                        note_like = item.locator(self.config.like_count_selector).inner_text()
                        # 缩略图
                        note_img = item.locator(self.config.image_selector).nth(0).get_attribute("src")
                        # 笔记链接
                        note_href = item.locator(self.config.cover_selector).get_attribute("href")
                        # 获取当前笔记的时间
                        note_time = datetime.now().strftime(f"%Y-%m-%d %H:%M:%S")

                        print(f"当前为第{self.scroll_count}轮滚动时的第{i}个笔记, 获取时间{note_time}\n标题{note_title}\n作者{note_author}\n喜欢{note_like}\n预览图{note_img}\n笔记链接https://www.xiaohongshu.com{note_href}\n")

                        # 去重：基于 JSON 文档（优先使用链接作为唯一键）
                        note_key = note_href if note_href else f"{note_title}{note_author}"
                        if self.storage.contains(note_key):
                            print("该笔记已在JSON记录中，跳过。\n")
                            continue
                        else:
                            # 评论的主逻辑
                            print("等待并点击进入笔记（使用选择器）")
                            cover = wait_until("进入笔记按钮", lambda: item.locator(self.config.cover_selector))
                            cover.click()
                            page.wait_for_timeout(self.human_wait())
                            
                            # 关注 → 点赞 → 收藏（每步人类化移动与等待）
                            try:
                                print("准备关注作者（选择器点击）")
                                follow_btn = wait_until("关注按钮", lambda: page.locator(self.config.follow_button_selector))
                                follow_btn.click()
                                page.wait_for_timeout(self.human_wait())
                            except Exception as e:
                                print(f"关注步骤异常：{e}，暂停等待人工继续...")
                                input("按回车继续...")

                            try:
                                print("准备点赞（选择器点击）")
                                like_btn = wait_until("点赞按钮", lambda: page.locator(self.config.like_button_selector))
                                like_btn.click()
                                page.wait_for_timeout(self.human_wait())
                            except Exception as e:
                                print(f"点赞步骤异常：{e}，暂停等待人工继续...")
                                input("按回车继续...")

                            # try:
                            #     print("准备收藏")
                            #     cx, cy = self.humanizer.move_mouse_bezier_to(page, page.locator(self.config.collect_button_selector))
                            #     page.wait_for_timeout(self.human_wait())
                            #     if cx is not None and cy is not None:
                            #         page.mouse.click(cx, cy)
                            #     else:
                            #         page.locator(self.config.collect_button_selector).click()
                            #     page.wait_for_timeout(self.human_wait())
                            # except Exception:
                            #     print("收藏按钮未正常点击，跳过")

                            love1 = self.loveword()
                            print(f"正在填充评论(1/2，仅情话)...\n评论内容: {love1}")
                            textarea = wait_until("评论输入框", lambda: page.locator(self.config.comment_textarea_selector))
                            textarea.fill(f"{love1}[红色心形R]")
                            page.wait_for_timeout(self.human_wait())

                            print("正在发送评论(1/2)...")
                            textarea.press("Enter")
                            page.wait_for_timeout(self.human_wait())

                            # 第二条：从模板中随机选一条
                            love2 = self.loveword()
                            tpl = random.choice(self.config.comment_templates)
                            text2 = tpl.format(love=love2)
                            print(f"正在填充评论(2/2，模板)...\n评论内容: {text2}")
                            textarea = wait_until("评论输入框", lambda: page.locator(self.config.comment_textarea_selector))
                            textarea.fill(text2)
                            page.wait_for_timeout(self.human_wait())

                            print("正在发送评论(2/2)...")
                            textarea.press("Enter")
                            page.wait_for_timeout(self.human_wait())

                            print("正在退出笔记（选择器点击）")
                            close_btn = wait_until("关闭按钮", lambda: page.locator(self.config.close_selector))
                            close_btn.click()
                            page.wait_for_timeout(self.human_wait())

                            # 成功后写入 JSON 文档（实时）
                            self.storage.add(note_key, {
                                "title": note_title,
                                "author": note_author,
                                "like": note_like,
                                "img": note_img,
                                "href": note_href,
                                "comment": love1,
                                "commented_at": note_time
                            })
                            print(f"已评论{len(self.storage._data)}条笔记!\n\n")
                    
                except Exception as e:
                    print(f"获取探索页容器失败或流程异常：{e}")
                    input("流程已暂停，请手动调整页面或网络后按回车继续...")
                    continue

                # 本批评论完成后，再小步滚动一次并短暂停顿
                page.mouse.wheel(0, random.randint(self.config.wheel_delta_min, self.config.wheel_delta_max))
                page.wait_for_timeout(random.randint(self.config.scroll_pause_ms_min, self.config.scroll_pause_ms_max))
                self.scroll_count = self.scroll_count + 1
                remaining_min = max(0, int((end_time - datetime.now()).total_seconds() // 60))
                print(f"🚀🚀🚀 本批完成后第{self.scroll_count}次小步滚动（剩余约{remaining_min}分钟） 🚀🚀🚀")
            input(f"已达到设定的{M}分钟, 回车结束程序。")
                    
if __name__ == "__main__":
    XHS_Post = Bottle()
    XHS_Post.Post()