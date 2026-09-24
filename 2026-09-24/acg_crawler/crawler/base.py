"""基础爬虫类"""
import time
import random
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 验证页特征（状态码200但内容是验证/登录页）
VERIFY_PAGE_HINTS = ["cloudflare", "captcha", "verify", "just a moment",
                     "请完成验证", "访问受限", "登录后查看", "人机验证"]

class BaseCrawler(ABC):
    """爬虫基类"""

    def __init__(self, config):
        self.config = config
        self.site_name = ""
        self.base_url = ""
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self._consecutive_failures = 0
        self._paused_until = 0.0
        self._setup_proxy()

    def _setup_proxy(self):
        self._proxy_enabled = self.config.get("proxy", {}).get("enabled", False)
        if self._proxy_enabled:
            proxy = self.config["proxy"]["http"]
            # 启动时探测代理端口是否可达：代理软件没开时自动退回直连，
            # 避免所有请求（含登录POST）被 ProxyError 打死
            if not self._proxy_reachable(proxy):
                print(f"[{self.site_name}] 代理 {proxy} 不可用，本次自动改用直连")
                self._proxy_enabled = False
                return
            self.session.proxies = {"http": proxy, "https": proxy}

    @staticmethod
    def _proxy_reachable(proxy_url):
        """TCP 探测代理端口（1秒超时）"""
        import socket
        from urllib.parse import urlparse
        try:
            p = urlparse(proxy_url)
            host = p.hostname or "127.0.0.1"
            port = p.port or 7890
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            try:
                s.connect((host, port))
                return True
            finally:
                s.close()
        except Exception:
            return False

    def _delay(self):
        min_delay = self.config.get("crawler", {}).get("request_delay_min", 0.5)
        max_delay = self.config.get("crawler", {}).get("request_delay_max", 1.5)
        time.sleep(random.uniform(min_delay, max_delay))

    def _throttle_on_failure(self):
        """连续失败后指数退避，熔断保护"""
        self._consecutive_failures += 1
        if self._consecutive_failures >= 5:
            # 连续5次失败：暂停30秒
            self._paused_until = time.time() + 30
            self._consecutive_failures = 0
        elif self._consecutive_failures >= 3:
            # 连续3次失败：退避2^n秒
            time.sleep(min(2 ** self._consecutive_failures, 8))

    def _reset_failures(self):
        self._consecutive_failures = 0

    def _check_pause(self):
        """检查是否处于熔断暂停期"""
        if self._paused_until > time.time():
            time.sleep(self._paused_until - time.time())
            self._paused_until = 0.0

    def _is_verify_page(self, resp):
        """检测状态码200的验证页/异常空页面"""
        if resp.status_code != 200:
            return False
        text = resp.text[:3000].lower()
        if any(hint in text for hint in VERIFY_PAGE_HINTS):
            return True
        # 页面过短且无实质内容
        if len(resp.text) < 200:
            return True
        return False

    def _request(self, url, retries=3):
        for attempt in range(retries):
            self._check_pause()
            try:
                self._delay()
                resp = self.session.get(url, timeout=self.config.get("crawler", {}).get("timeout", 15))
                resp.raise_for_status()
                if self._is_verify_page(resp):
                    raise requests.RequestException(f"检测到验证页: {url}")
                self._reset_failures()
                return resp
            except Exception as e:
                self._throttle_on_failure()
                # 代理失败时尝试直连
                if self._proxy_enabled and attempt == 0:
                    try:
                        old_proxies = self.session.proxies.copy()
                        self.session.proxies = {}
                        resp = self.session.get(url, timeout=self.config.get("crawler", {}).get("timeout", 15))
                        self.session.proxies = old_proxies
                        resp.raise_for_status()
                        if self._is_verify_page(resp):
                            raise requests.RequestException(f"检测到验证页: {url}")
                        self._reset_failures()
                        return resp
                    except:
                        self.session.proxies = old_proxies
                if attempt < retries - 1:
                    time.sleep(self.config.get("crawler", {}).get("retry_delay", 2) * (attempt + 1))
                else:
                    raise

    def _soup(self, url):
        resp = self._request(url)
        return BeautifulSoup(resp.text, "lxml")

    @abstractmethod
    def get_list_page(self, page_num):
        """获取列表页的帖子列表，返回帖子URL列表"""
        pass

    @abstractmethod
    def parse_detail(self, url, category=""):
        """解析详情页，返回帖子数据字典"""
        pass

    @abstractmethod
    def get_total_pages(self):
        """获取总页数"""
        pass

    def crawl_page(self, page_num):
        """爬取指定页码的所有帖子"""
        results = []
        try:
            urls = self.get_list_page(page_num)
            for url in urls:
                try:
                    post = self.parse_detail(url)
                    if post:
                        results.append(post)
                except Exception as e:
                    print(f"[{self.site_name}] 解析失败 {url}: {e}")
        except Exception as e:
            print(f"[{self.site_name}] 第{page_num}页获取失败: {e}")
        return results

    def crawl_date_range(self, start_date, end_date):
        """按日期范围爬取（需要遍历所有页面直到找到超出范围的帖子）"""
        results = []
        page = 1
        max_pages = self.get_total_pages()

        while page <= max_pages:
            try:
                urls = self.get_list_page(page)
                for url in urls:
                    try:
                        post = self.parse_detail(url)
                        if post:
                            post_date = post.get("post_date", "")
                            if post_date and post_date >= start_date and post_date <= end_date:
                                results.append(post)
                            elif post_date and post_date < start_date:
                                return results
                    except Exception as e:
                        print(f"[{self.site_name}] 解析失败 {url}: {e}")
                page += 1
            except Exception as e:
                print(f"[{self.site_name}] 第{page}页获取失败: {e}")
                page += 1

        return results
