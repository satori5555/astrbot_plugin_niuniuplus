import random
import yaml
import os
import re
import time
import json
import asyncio
import datetime
import sys
from astrbot.api.all import *

# 添加当前目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if (current_dir not in sys.path):
    sys.path.append(current_dir)
from sign_image import SignImageGenerator

# 添加商城模块导入
from niuniu_shop import NiuniuShop
# 添加定时测试模块导入
from timer_test import TimerTest
# 添加红包模块导入
from niuniu_redpacket import NiuniuRedPacket
# 添加集市模块导入
from niuniu_market import NiuniuMarket

# 常量定义
PLUGIN_DIR = os.path.join('data', 'plugins', 'astrbot_plugin_niuniu')
os.makedirs(PLUGIN_DIR, exist_ok=True)
NIUNIU_LENGTHS_FILE = os.path.join('data', 'niuniu_lengths.yml')
NIUNIU_TEXTS_FILE = os.path.join(PLUGIN_DIR, 'niuniu_game_texts.yml')
LAST_ACTION_FILE = os.path.join(PLUGIN_DIR, 'last_actions.yml')
LOCK_COOLDOWN = 300  # 锁牛牛冷却时间 5分钟

@register("niuniu_plugin", "长安某", "牛牛插件，包含注册牛牛、打胶、我的牛牛、比划比划、牛牛排行等功能", "3.4.2")
class NiuniuPlugin(Star):
    # 冷却时间常量（秒）
    COOLDOWN_10_MIN = 600    # 10分钟
    COOLDOWN_30_MIN = 1800   # 30分钟
    COMPARE_COOLDOWN = 180   # 比划冷却
    LOCK_COOLDOWN = 300      # 锁牛牛冷却时间 5分钟
    INVITE_LIMIT = 3         # 邀请次数限制
    MAX_WORK_HOURS = 6       # 最大打工时长（小时）
    WORK_REWARD_INTERVAL = 600  # 打工奖励间隔（秒）
    WORK_REWARD_COINS = 5     # 每10分钟打工奖励金币数

    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.niuniu_lengths = self._load_niuniu_lengths()
        self.niuniu_texts = self._load_niuniu_texts()
        self.last_dajiao_time = {}      # {str(group_id): {str(user_id): last_time}}
        self.last_compare_time = {}     # {str(group_id): {str(user_id): {str(target_id): last_time}}}
        self.last_actions = self._load_last_actions()
        self.admins = self._load_admins()  # 加载管理员列表
        self.working_users = {}  # {str(group_id): {str(user_id): {start_time: float, duration: int}}}
        # 初始化商城实例
        self.shop = NiuniuShop(self)
        # 初始化定时测试模块
        self.timer_test = TimerTest(context)
        # 初始化红包模块
        self.redpacket = NiuniuRedPacket(self)
        # 初始化牛牛集市
        self.market = NiuniuMarket(self)
        
        # 启动贞操锁监控任务
        asyncio.create_task(self.shop.monitor_chastity_locks())
        # 启动变性手术监控任务
        asyncio.create_task(self.shop.monitor_gender_surgeries())

    # region 数据管理
    def _create_niuniu_lengths_file(self):
        """创建数据文件"""
        try:
            with open(NIUNIU_LENGTHS_FILE, 'w', encoding='utf-8') as f:
                yaml.dump({}, f)
        except Exception as e:
            self.context.logger.error(f"创建文件失败: {str(e)}")

    def _load_niuniu_lengths(self):
        """加载牛牛数据"""
        if not os.path.exists(NIUNIU_LENGTHS_FILE):
            self._create_niuniu_lengths_file()
        
        try:
            with open(NIUNIU_LENGTHS_FILE, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            # 数据结构验证
            for group_id in list(data.keys()):
                group_data = data[group_id]
                if not isinstance(group_data, dict):
                    data[group_id] = {'plugin_enabled': False}
                elif 'plugin_enabled' not in group_data:
                    group_data['plugin_enabled'] = False
            return data
        except Exception as e:
            self.context.logger.error(f"加载数据失败: {str(e)}")
            return {}

    def _load_niuniu_texts(self):
        """加载游戏文本"""
        default_texts = {
            'register': {
                'success': "🧧 {nickname} 成功注册牛牛！\n📏 初始长度：{length}cm\n💪 硬度等级：{hardness}",
                'already_registered': "⚠️ {nickname} 你已经注册过牛牛啦！",
            },
            'dajiao': {
                'cooldown': [
                    "⏳ {nickname} 牛牛需要休息，{remaining}分钟后可再打胶",
                    "🛑 冷却中，{nickname} 请耐心等待 (＞﹏＜)"
                ],
                'increase': [
                    "🚀 {nickname} 打胶成功！长度增加 {change}cm！",
                    "🎉 {nickname} 的牛牛茁壮成长！+{change}cm"
                ],
                'decrease': [
                    "😱 {nickname} 用力过猛！长度减少 {change}cm！",
                    "⚠️ {nickname} 操作失误！-{change}cm"
                ],
                'decrease_30min': [
                    "😱 {nickname} 用力过猛！长度减少 {change}cm！",
                    "⚠️ {nickname} 操作失误！-{change}cm"
                ],
                'no_effect': [
                    "🌀 {nickname} 的牛牛毫无变化...",
                    "🔄 {nickname} 这次打胶没有效果"
                ],
                'not_registered': "❌ {nickname} 请先注册牛牛"
            },
            'my_niuniu': {
                'info': "📊 {nickname} 的牛牛状态\n📏 长度：{length}\n💪 硬度：{hardness}\n📝 评价：{evaluation}",
                'evaluation': {
                    'short': ["小巧玲珑", "精致可爱"],
                    'medium': ["中规中矩", "潜力无限"],
                    'long': ["威风凛凛", "傲视群雄"],
                    'very_long': ["擎天巨柱", "突破天际"],
                    'super_long': ["超级长", "无与伦比"],
                    'ultra_long': ["超越极限", "无人能敌"]
                },
                'not_registered': "❌ {nickname} 请先注册牛牛"
            },
            'compare': {
                'no_target': "❌ {nickname} 请指定比划对象",
                'target_not_registered': "❌ 对方尚未注册牛牛",
                'cooldown': "⏳ {nickname} 请等待{remaining}分钟后再比划",
                'self_compare': "❌ 不能和自己比划",
                'win': [
                    "🏆 {nickname} 的牛牛更胜一筹！+{gain}cm"
                ],
                'lose': [
                    "💔 {nickname} 的牛牛不敌对方！-{loss}cm"
                ],
                'draw': "🤝 双方势均力敌！",
                'double_loss': "😱 {nickname1} 和 {nickname2} 的牛牛因过于柔软发生缠绕，长度减半！",
                'hardness_win': "🎉 {nickname} 因硬度优势获胜！",
                'hardness_lose': "💔 {nickname} 因硬度劣势败北！",
                'user_no_increase': "😅 {nickname} 的牛牛没有任何增长。"
            },
            'ranking': {
                'header': "🏅 牛牛排行榜 TOP10：\n",
                'no_data': "📭 本群暂无牛牛数据",
                'item': "{rank}. {name} ➜ {length}"
            },
            'menu': {
                'default': """📜 牛牛菜单：
🔹 注册牛牛 - 初始化你的牛牛
🔹 打胶 - 提升牛牛长度
🔹 我的牛牛 - 查看当前状态
🔹 锁牛牛 @目标 - 锁他牛牛
🔹 比划比划 @目标 - 发起对决
🔹 牛牛排行 - 查看群排行榜
🔹 每日签到 - 领取金币奖励
🔹 牛牛商城 - 购买强力道具
🔹 牛牛背包 - 查看拥有道具
🔹 打工 - 赚取金币
🔹 送金币 @对方 - 转赠金币
🔹 牛牛开/关 - 管理插件"""
            },
            'system': {
                'enable': "✅ 牛牛插件已启用",
                'disable': "❌ 牛牛插件已禁用"
            },
            'lock': {
                'cooldown': "⏳ {nickname} 请等待{remaining}分钟后再锁牛牛",
                'no_target': "❌ {nickname} 请指定要锁的目标",
                'target_not_registered': "❌ 对方尚未注册牛牛",
                'self_lock': "❌ 不能锁自己的牛牛",
                'decrease': "😱 {target_nickname} 的牛牛被 {nickname} 的小嘴牢牢锁了！长度减少 {change}cm！",
                'increase': "😂 {target_nickname} 的牛牛被 {nickname} 锁爽了！增加 {change}cm！",
                'break': "💔 {target_nickname} 的牛牛被 {nickname} 锁断了！长度减少一半！",
                'no_effect': "😅 {target_nickname} 的牛牛完美躲过了 {nickname} 嘴巴！"
            },
            'transfer': {
                'no_target': "❌ 请指定转赠对象",
                'target_not_registered': "❌ 对方尚未注册牛牛",
                'self_transfer': "❌ 不能给自己转赠金币",
                'invalid_amount': "❌ 请输入有效的金币数量",
                'insufficient_coins': "❌ 你的金币不足",
                'not_registered': "❌ 请先注册牛牛",
                'success': "💰 成功转赠 {amount} 金币给 {target_nickname}\n你的余额: {user_balance}\n对方余额: {target_balance}"
            }
        }
        
        try:
            if os.path.exists(NIUNIU_TEXTS_FILE):
                with open(NIUNIU_TEXTS_FILE, 'r', encoding='utf-8') as f:
                    custom_texts = yaml.safe_load(f) or {}
                    return self._deep_merge(default_texts, custom_texts)
        except Exception as e:
            self.context.logger.error(f"加载文本失败: {str(e)}")
        return default_texts

    def _deep_merge(self, base, update):
        """深度合并字典"""
        for key, value in update.items():
            if isinstance(value, dict):
                base[key] = self._deep_merge(base.get(key, {}), value)
            else:
                base[key] = value
        return base

    def _save_niuniu_lengths(self):
        """保存数据"""
        try:
            with open(NIUNIU_LENGTHS_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(self.niuniu_lengths, f, allow_unicode=True)
        except Exception as e:
            self.context.logger.error(f"保存失败: {str(e)}")

    def _load_last_actions(self):
        """加载冷却数据"""
        try:
            with open(LAST_ACTION_FILE, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except:
            return {}

    def _save_last_actions(self):
        """保存冷却数据"""
        try:
            with open(LAST_ACTION_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(self.last_actions, f, allow_unicode=True)
        except Exception as e:
            self.context.logger.error(f"保存冷却数据失败: {str(e)}")

    def _load_admins(self):
        """加载管理员列表"""
        try:
            with open(os.path.join('data', 'cmd_config.json'), 'r', encoding='utf-8-sig') as f:
                config = json.load(f)
                return config.get('admins_id', [])
        except Exception as e:
            self.context.logger.error(f"加载管理员列表失败: {str(e)}")
            return []

    def is_admin(self, user_id):
        """检查用户是否为管理员"""
        return str(user_id) in self.admins
    # endregion

    # region 工具方法
    def format_length(self, length):
        """格式化长度显示"""
        if length >= 100:
            return f"{length/100:.2f}m"
        return f"{length}cm"

    def get_group_data(self, group_id):
        """获取群组数据"""
        group_id = str(group_id)
        if group_id not in self.niuniu_lengths:
            self.niuniu_lengths[group_id] = {'plugin_enabled': False}  # 默认关闭插件
        return self.niuniu_lengths[group_id]

    def get_user_data(self, group_id, user_id):
        """获取用户数据"""
        group_data = self.get_group_data(group_id)
        user_id = str(user_id)
        return group_data.get(user_id)

    def check_cooldown(self, last_time, cooldown):
        """检查冷却时间"""
        current = time.time()
        elapsed = current - last_time
        remaining = cooldown - elapsed
        return remaining > 0, remaining

    def parse_at_target(self, event):
        """解析@目标"""
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                return str(comp.qq)
        return None

    def parse_target(self, event):
        """解析@目标或用户名"""
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                return str(comp.qq)
        msg = event.message_str.strip()
        if msg.startswith("比划比划"):
            target_name = msg[len("比划比划"):].strip()
            if target_name:
                group_id = str(event.message_obj.group_id)
                group_data = self.get_group_data(group_id)
                for user_id, user_data in group_data.items():
                    if isinstance(user_data, dict):  # 检查 user_data 是否为字典
                        nickname = user_data.get('nickname', '')
                        if re.search(re.escape(target_name), nickname, re.IGNORECASE):
                            return user_id
        return None

    def parse_lock_target(self, event):
        """解析锁牛牛的@目标或用户名"""
        # 先尝试获取@的用户
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                return str(comp.qq)
                
        # 如果没有@，则解析消息中的用户名
        msg = event.message_str.strip()
        if msg.startswith("锁牛牛"):
            target_name = msg[len("锁牛牛"):].strip()
            if target_name:
                group_id = str(event.message_obj.group_id)
                group_data = self.get_group_data(group_id)
                for user_id, user_data in group_data.items():
                    if not isinstance(user_data, dict) or 'nickname' not in user_data:
                        continue
                    nickname = user_data.get('nickname', '')
                    if nickname and target_name in nickname:
                        return user_id
        return None

    # 在 NiuniuPlugin 类中添加等待消息的辅助方法
    async def wait_for_message(self, event, check, timeout=30):
        """等待用户回复"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                new_event = await self.context.wait_next_event(1)
                if (isinstance(new_event, AstrMessageEvent) and 
                    new_event.message_obj.group_id == event.message_obj.group_id and
                    new_event.get_sender_id() == event.get_sender_id() and
                    check(new_event)):
                    return new_event
            except TimeoutError:
                continue
        raise TimeoutError()
    # endregion

    # region 事件处理
    niuniu_commands = ["牛牛菜单", "牛牛开", "牛牛关", "注册牛牛", "打胶", "我的牛牛", "比划比划", "牛牛排行", "锁牛牛", "打工", "打工时间", "牛牛日历", 
                       "牛牛集市", "查看集市", "上架牛牛", "购买牛牛", "回收牛牛"]

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """群聊消息处理器"""
        group_id = str(event.message_obj.group_id)
        msg = event.message_str.strip()

        # 添加独立测试命令，不需要牛牛插件启用
        if msg == "定时测试":
            async for result in self.timer_test.test_timer(event):
                yield result
            return
            
        # 添加可以指定时间的定时测试
        match = re.match(r'^定时测试\s+(\d+)(?:分钟)?$', msg)
        if match:
            minutes = int(match.group(1))
            if 1 <= minutes <= 60:  # 限制在1-60分钟之间
                async for result in self.timer_test.test_timer(event, minutes):
                    yield result
                return
            else:
                yield event.plain_result("⚠️ 定时测试时间需要在1-60分钟之间")
                return

        # 添加1分钟测试命令
        if msg == "1分钟":
            async for result in self._work_test(event):
                yield result
            return

        # 添加购买命令的处理
        if msg.startswith("购买"):
            # 将购买命令直接传递给shop模块处理
            async for result in self.shop.process_purchase_command(event):
                yield result
            return
        
        # 添加绝育命令处理
        if msg.startswith("绝育"):
            async for result in self._handle_sterilization(event):
                yield result
            return
            
        # 添加解锁命令处理
        if msg == "解锁绝育":
            async for result in self.shop.unlock_sterilization(event):
                yield result
            return
            
        # 添加调换命令处理
        if msg.startswith("调换"):
            async for result in self._handle_exchange(event):
                yield result
            return
        
        # 添加背包命令
        if msg.startswith("牛牛背包"):
            async for result in self.shop.show_backpack(event):
                yield result
            return

        # 添加红包相关命令处理
        if msg.startswith("发红包"):
            async for result in self.redpacket.handle_send_red_packet(event):
                yield result
            return
            
        if msg == "抢红包":
            async for result in self.redpacket.handle_grab_red_packet(event):
                yield result
            return

        # 添加扣豆命令处理
        if msg.startswith("扣"):
            async for result in self._handle_kou_doudou(event):
                yield result
            return

        # 添加牛牛集市相关命令处理
        if msg == "牛牛集市" or msg.startswith("上架牛牛") or msg == "查看集市" or msg.startswith("购买牛牛") or msg == "回收牛牛":
            async for result in self.market.process_market_command(event):
                yield result
            return

        handler_map = {
            "牛牛菜单": self._show_menu,
            "牛牛开": lambda event: self._toggle_plugin(event, True),
            "牛牛关": lambda event: self._toggle_plugin(event, False),
            "注册牛牛": self._register,
            "打胶": self._dajiao,
            "我的牛牛": self._show_status,
            "比划比划": self._compare,
            "牛牛排行": self._show_ranking,
            "锁牛牛": self._lock_niuniu,
            "每日签到": self._daily_sign,      
            "牛牛商城": self._show_shop,
            "牛牛背包": lambda event: self.shop.show_backpack(event),
            "送金币": self._transfer_coins,  # 添加金币转赠命令
            "打工时间": self._check_work_time,
            "打工": self._work,
            "牛牛日历": self._view_sign_calendar
        }

        for cmd, handler in handler_map.items():
            if msg.startswith(cmd):
                async for result in handler(event):
                    yield result
                return

    @event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def on_private_message(self, event: AstrMessageEvent):
        """私聊消息处理器"""
        msg = event.message_str.strip()
        niuniu_commands = ["牛牛菜单", "牛牛开", "牛牛关", "注册牛牛", "打胶", "我的牛牛", "比划比划", "牛牛排行","锁牛牛"]
        
        if any(msg.startswith(cmd) for cmd in niuniu_commands):
            yield event.plain_result("不许一个人偷偷玩牛牛")
        else:
            return
    def _is_user_working(self, group_id, user_id):
        """检查用户是否在打工中"""
        group_id, user_id = str(group_id), str(user_id)
        current_time = time.time()
        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        work_data = user_actions.get('work_data')
        
        if work_data:
            elapsed_time = current_time - work_data['start_time']
            return elapsed_time < work_data['duration'] * 3600
        return False

    def _get_daily_work_time(self, group_id, user_id):
        """获取用户当日已打工时长（小时）"""
        group_id, user_id = str(group_id), str(user_id)
        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        work_data = user_actions.get('work_data')
        
        if not work_data:
            return 0
            
        current_time = time.time()
        today_start = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, 0))

        if work_data['start_time'] < today_start:
            return 0

        return min(work_data['duration'], 
                  (current_time - work_data['start_time']) / 3600)

    async def _work(self, event):
        """打工功能"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            chain = [
                At(qq=event.get_sender_id()),
                Plain("\n❌ 插件未启用")
            ]
            yield event.chain_result(chain)
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            chain = [
                At(qq=event.get_sender_id()),
                Plain("\n❌ 请先注册牛牛")
            ]
            yield event.chain_result(chain)
            return

        # 检查是否已在打工中
        if self._is_user_working(group_id, user_id):
            chain = [
                At(qq=event.get_sender_id()),
                Plain(f"\n小南娘：{nickname}，你已经在工作中了哦~")
            ]
            yield event.chain_result(chain)
            return

        # 解析打工时长
        msg = event.message_str.strip()
        match = re.search(r'打工\s*(\d+)\s*小时', msg)
        if not match:
            chain = [
                At(qq=event.get_sender_id()),
                Plain("\n❌ 请输入正确的打工时长，例如：打工 2小时")
            ]
            yield event.chain_result(chain)
            return

        hours = int(match.group(1))
        if hours <= 0:
            chain = [
                At(qq=event.get_sender_id()),
                Plain("\n❌ 打工时长必须大于0小时")
            ]
            yield event.chain_result(chain)
            return
            
        if hours > self.MAX_WORK_HOURS:
            chain = [
                At(qq=event.get_sender_id()),
                Plain(f"\n❌ 单次打工时长不能超过{self.MAX_WORK_HOURS}小时")
            ]
            yield event.chain_result(chain)
            return

        # 检查每日打工时长限制
        daily_work_time = self._get_daily_work_time(group_id, user_id)
        remaining_hours = self.MAX_WORK_HOURS - daily_work_time
        if remaining_hours <= 0:
            chain = [
                At(qq=event.get_sender_id()),
                Plain(f"\n❌ 今日打工时长已达上限{self.MAX_WORK_HOURS}小时")
            ]
            yield event.chain_result(chain)
            return
        if hours > remaining_hours:
            chain = [
                At(qq=event.get_sender_id()),
                Plain(f"\n❌ 今日只能再打工{remaining_hours:.1f}小时")
            ]
            yield event.chain_result(chain)
            return

        # 获取打工倍率（变性状态下翻倍）
        multiplier = self.shop.get_work_multiplier(group_id, user_id)
        
        # 直接计算并发放金币奖励
        coins_per_hour = (3600 // self.WORK_REWARD_INTERVAL) * self.WORK_REWARD_COINS
        total_coins = int(coins_per_hour * hours * multiplier)
        
        # 更新用户金币
        user_data['coins'] = user_data.get('coins', 0) + total_coins
        self._save_niuniu_lengths()
        
        # 记录打工信息到last_actions
        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        user_actions['work_data'] = {
            'start_time': time.time(),
            'duration': hours
        }
        self._save_last_actions()
        
        # 储存打工结束消息的会话ID
        unified_msg_origin = event.unified_msg_origin
        
        # 发送开始打工的消息
        chain = [
            At(qq=event.get_sender_id()),
            Plain(f"\n小南娘：{nickname}要去陪客户{hours}小时，已经提前拿到{total_coins}金币啦~\n现在金币余额：{user_data['coins']}💰\n(打工期间无法使用其他牛牛功能)")
        ]
        yield event.chain_result(chain)

        # 创建并存储异步任务，使用与timer_test相似的方式
        task_id = f"work_{group_id}_{user_id}_{int(time.time())}"
        task = asyncio.create_task(self._work_timer_improved(
            group_id=group_id,
            user_id=user_id,
            nickname=nickname,
            unified_msg_origin=unified_msg_origin,
            delay_seconds=int(hours * 3600)
        ))
        
        # 存储任务引用，防止被垃圾回收
        if not hasattr(self, '_work_tasks'):
            self._work_tasks = {}
        self._work_tasks[task_id] = task
        
        # 设置清理回调
        task.add_done_callback(lambda t: self._work_tasks.pop(task_id, None))

    async def _work_test(self, event):
        """打工测试功能 - 1分钟后自动完成"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        # 检查是否已在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，你已经在工作中了哦~")
            return

        # 固定1分钟测试时间
        minutes = 1
        hours = minutes / 60
        
        # 获取打工倍率（变性状态下翻倍）
        multiplier = self.shop.get_work_multiplier(group_id, user_id)
        
        # 直接计算并发放金币奖励
        coins_per_hour = (3600 // self.WORK_REWARD_INTERVAL) * self.WORK_REWARD_COINS
        total_coins = int(coins_per_hour * hours * multiplier)
        
        # 更新用户金币
        user_data['coins'] = user_data.get('coins', 0) + total_coins
        self._save_niuniu_lengths()
        
        # 记录打工信息到last_actions
        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        user_actions['work_data'] = {
            'start_time': time.time(),
            'duration': hours,
            'is_test': True  # 标记为测试
        }
        self._save_last_actions()
        
        # 储存打工结束消息的会话ID
        unified_msg_origin = event.unified_msg_origin
        
        # 发送开始打工的消息
        yield event.plain_result(f"🧪 测试模式：{nickname}开始打工测试，将在{minutes}分钟后结束。\n💰 获得{total_coins}金币\n现在金币余额：{user_data['coins']}💰")

        # 创建并存储异步任务，使用与定时测试相似的方式
        task_id = f"work_test_{group_id}_{user_id}_{int(time.time())}"
        task = asyncio.create_task(self._work_timer_improved(
            group_id=group_id,
            user_id=user_id,
            nickname=nickname,
            unified_msg_origin=unified_msg_origin,
            delay_seconds=int(minutes * 60)
        ))
        
        # 存储任务引用，防止被垃圾回收
        if not hasattr(self, '_work_tasks'):
            self._work_tasks = {}
        self._work_tasks[task_id] = task
        
        # 设置清理回调
        task.add_done_callback(lambda t: self._work_tasks.pop(task_id, None))

    async def _work_timer_improved(self, group_id, user_id, nickname, unified_msg_origin, delay_seconds):
        """改进版的打工定时器，采用与定时测试相同的实现方式"""
        try:
            # 等待指定时间
            await asyncio.sleep(delay_seconds)
            
            # 构建消息链
            message_chain = MessageChain([
                At(qq=user_id),
                Plain(f" 小南娘：{nickname}，你的工作时间结束了哦~")
            ])
            
            # 直接发送消息
            await self.context.send_message(unified_msg_origin, message_chain)
            
            # 记录日志
            self.context.logger.info(f"已向用户 {user_id} 发送打工结束提醒")
            
            # 清理用户的打工状态
            try:
                user_actions = self.last_actions.get(group_id, {}).get(user_id, {})
                if 'work_data' in user_actions:
                    del user_actions['work_data']
                    self._save_last_actions()
            except Exception as e:
                self.context.logger.error(f"清理打工状态失败: {e}")
                
        except Exception as e:
            self.context.logger.error(f"打工定时器执行异常: {e}")

    async def _check_work_time(self, event):
        """查看打工时间"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            chain = [
                At(qq=event.get_sender_id()),
                Plain("\n❌ 插件未启用")
            ]
            yield event.chain_result(chain)
            return

        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        work_data = user_actions.get('work_data')
        
        if not work_data or not self._is_user_working(group_id, user_id):
            chain = [
                At(qq=event.get_sender_id()),
                Plain(f"\n小南娘：{nickname}，你现在没有在工作哦~")
            ]
            yield event.chain_result(chain)
            return

        current_time = time.time()
        end_time = work_data['start_time'] + work_data['duration'] * 3600
        remaining_seconds = end_time - current_time

        remaining_hours = int(remaining_seconds // 3600)
        remaining_minutes = int((remaining_seconds % 3600) // 60)

        chain = [
            At(qq=event.get_sender_id()),
            Plain(f"\n小南娘：{nickname}，客户还要和你快乐{remaining_hours}小时{remaining_minutes}分哦~")
        ]
        yield event.chain_result(chain)

    # endregion

    # region 核心功能
    async def _toggle_plugin(self, event, enable):
        """开关插件"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        # 检查是否为管理员
        if not self.is_admin(user_id):
            yield event.plain_result("❌ 只有管理员才能使用此指令")
            return

        self.get_group_data(group_id)['plugin_enabled'] = enable
        self._save_niuniu_lengths()
        text_key = 'enable' if enable else 'disable'
        yield event.plain_result(self.niuniu_texts['system'][text_key])

    async def _register(self, event):
        """注册牛牛"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        if user_id in group_data:
            text = self.niuniu_texts['register']['already_registered'].format(nickname=nickname)
            yield event.plain_result(text)
            return

        cfg = self.config.get('niuniu_config', {})
        group_data[user_id] = {
            'nickname': nickname,
            'length': random.randint(cfg.get('min_length', 3), cfg.get('max_length', 10)),
            'hardness': 1,
            'coins': 0,  # 添加金币字段
            'last_sign': 0,  # 上次签到时间
            'items': {  # 道具状态
                'viagra': 0,     # 伟哥剩余次数
                'surgery': False,  # 是否已使用手术
                'pills': False    # 是否有六味地黄丸效果
            }
        }
        self._save_niuniu_lengths()

        text = self.niuniu_texts['register']['success'].format(
            nickname=nickname,
            length=group_data[user_id]['length'],
            hardness=group_data[user_id]['hardness']
        )
        yield event.plain_result(text)

    async def _dajiao(self, event):
        """打胶功能"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            text = self.niuniu_texts['dajiao']['not_registered'].format(nickname=nickname)
            yield event.plain_result(text)
            return

        # 检查用户是否在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候要认真哦！")
            return

        # 检查是否被绝育
        if self.shop.is_sterilized(group_id, user_id):
            yield event.plain_result(f"❌ {nickname}，你已被绝育，需要花费150金币解锁")
            return

        # 添加变性状态检查
        if self.shop.is_gender_surgery_active(group_id, user_id):
            yield event.plain_result(f"❌ {nickname}，变性状态下牛牛无法变长哦~")
            return

        # 获取当前时间
        current_time = time.time()
        
        # 冷却检查
        last_time = self.last_actions.setdefault(group_id, {}).get(user_id, {}).get('dajiao', 0)
        on_cooldown, remaining = self.check_cooldown(last_time, self.COOLDOWN_10_MIN)
        
        # 如果在冷却中，检查是否有伟哥可用
        if on_cooldown:
            # 尝试使用伟哥
            viagra_remaining = self.shop.use_viagra_for_dajiao(group_id, user_id)
            if viagra_remaining is not False:  # 伟哥使用成功，返回剩余次数
                # 伟哥效果固定增加长度10-20cm
                change = random.randint(10, 20)
                user_data['length'] += change
                # 更新最后打胶时间，但不影响冷却（伟哥特性）
                self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})['last_viagra_use'] = current_time
                self._save_last_actions()
                self._save_niuniu_lengths()
                
                # 添加剩余次数提示
                remaining_text = f"剩余{viagra_remaining}次" if viagra_remaining > 0 else "已用完"
                
                yield event.plain_result(
                    f"💊 使用伟哥打胶成功！({remaining_text})\n"
                    f"📏 长度增加: +{change}cm\n"
                    f"💪 当前长度: {self.format_length(user_data['length'])}"
                )
                return
            else:
                # 没有伟哥且在冷却中，提示等待
                mins = int(remaining // 60) + 1
                text = random.choice(self.niuniu_texts['dajiao']['cooldown']).format(
                    nickname=nickname,
                    remaining=mins
                )
                yield event.plain_result(text)
                return
        
        # 正常打胶逻辑（不在冷却或已过冷却）
        # 计算变化
        change = 0
        elapsed = current_time - last_time

        if elapsed < self.COOLDOWN_30_MIN:  # 10-30分钟
            rand = random.random()
            if rand < 0.4:   # 40% 增加
                change = random.randint(2, 5)
            elif rand < 0.7: # 30% 减少
                change = -random.randint(1, 3)
                template = random.choice(self.niuniu_texts['dajiao']['decrease'])
        else:  # 30分钟后
            rand = random.random()
            if rand < 0.7:  # 70% 增加
                change = random.randint(3, 6)
                user_data['hardness'] = min(user_data['hardness'] + 1, 10)
            elif rand < 0.9: # 20% 减少
                change = -random.randint(1, 2)
                template = random.choice(self.niuniu_texts['dajiao']['decrease_30min'])

        # 应用变化
        user_data['length'] = max(1, user_data['length'] + change)
        self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})['dajiao'] = current_time
        self._save_last_actions()
        self._save_niuniu_lengths()

        # 生成消息
        if change > 0:
            template = random.choice(self.niuniu_texts['dajiao']['increase'])
        elif change < 0:
            template = template  
        else:
            template = random.choice(self.niuniu_texts['dajiao']['no_effect'])

        text = template.format(nickname=nickname, change=abs(change))
        yield event.plain_result(f"{text}\n当前长度：{self.format_length(user_data['length'])}")

    async def _transfer_coins(self, event):
        """金币转赠功能"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 检查用户是否在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候要认真哦！")
            return

        # 检查自身是否注册
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result(self.niuniu_texts['transfer']['not_registered'])
            return

        # 解析目标用户和金币数量
        msg = event.message_str.strip()
        if msg.startswith("送金币"):
            msg = msg[len("送金币"):].strip()
        
        # 先尝试获取@的用户
        target_id = None
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                target_id = str(comp.qq)
                break
        
        # 如果没有@，尝试从消息中解析用户名
        if not target_id:
            # 尝试从消息中提取用户名和金额
            parts = msg.split()
            if len(parts) < 2:  # 至少需要用户名和金额
                yield event.plain_result(self.niuniu_texts['transfer']['no_target'])
                return
            
            target_name = parts[0]
            # 在群内查找匹配的用户
            for uid, data in group_data.items():
                if isinstance(data, dict) and 'nickname' in data:
                    if target_name in data['nickname']:
                        target_id = uid
                        break
        
        if not target_id:
            yield event.plain_result(self.niuniu_texts['transfer']['no_target'])
            return

        if target_id == user_id:
            yield event.plain_result(self.niuniu_texts['transfer']['self_transfer'])
            return

        # 获取目标数据
        target_data = self.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result(self.niuniu_texts['transfer']['target_not_registered'])
            return

        # 解析金币数量 - 查找最后一个数字
        amounts = []
        for part in msg.split():
            try:
                amount = int(part)
                amounts.append(amount)
            except ValueError:
                continue
        
        if not amounts:
            yield event.plain_result(self.niuniu_texts['transfer']['invalid_amount'])
            return
        
        amount = amounts[-1]  # 使用最后一个数字作为金额
        if amount <= 0:
            yield event.plain_result(self.niuniu_texts['transfer']['invalid_amount'])
            return

        # 检查金币是否足够
        if user_data.get('coins', 0) < amount:
            yield event.plain_result(self.niuniu_texts['transfer']['insufficient_coins'])
            return

        # 执行转赠
        user_data['coins'] -= amount
        target_data['coins'] = target_data.get('coins', 0) + amount
        self._save_niuniu_lengths()

        # 发送成功消息
        text = self.niuniu_texts['transfer']['success'].format(
            amount=amount,
            target_nickname=target_data['nickname'],
            user_balance=user_data['coins'],
            target_balance=target_data['coins']
        )
        yield event.plain_result(text)

    async def _daily_sign(self, event):
        """每日签到"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        # 检查用户是否在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候要认真哦！")
            return

        current_time = time.time()
        last_sign_time = user_data.get('last_sign', 0)
        
        # 检查是否在同一自然日内已经签到
        last_sign_date = datetime.datetime.fromtimestamp(last_sign_time).date()
        current_date = datetime.datetime.fromtimestamp(current_time).date()
        
        if last_sign_date == current_date:
            yield event.plain_result("⏳ 今天已经签到过了，明天再来吧~")
            return

        # 根据牛牛长度确定奖励
        length = user_data['length']
        if length >= 100:  # 1m以上
            coins = random.randint(30, 40)
        elif length >= 50:  # 50-100cm
            coins = random.randint(20, 30)
        else:  # 50cm以下
            coins = random.randint(10, 20)

        # 更新用户数据
        user_data['coins'] = user_data.get('coins', 0) + coins
        user_data['last_sign'] = current_time
        self._save_niuniu_lengths()

        # 生成签到图片
        try:
            # 使用已导入的SignImageGenerator
            sign_generator = SignImageGenerator()
            sign_generator.save_sign_record(user_id, group_id)
            sign_image_path = sign_generator.create_sign_image(nickname, coins, group_id)
            
            # 发送签到图片
            if (os.path.exists(sign_image_path)):
                yield event.image_result(sign_image_path)
            else:
                # 如果图片生成失败，发送文本消息
                yield event.plain_result(
                    f"✨ 签到成功！\n"
                    f"📏 当前牛牛长度：{self.format_length(length)}\n"
                    f"🪙 获得金币：{coins}\n"
                    f"💰 当前金币：{user_data['coins']}"
                )
        except Exception as e:
            print(f"生成签到图片失败: {str(e)}")
            # 发送文本消息作为备用
            yield event.plain_result(
                f"✨ 签到成功！\n"
                f"📏 当前牛牛长度：{self.format_length(length)}\n"
                f"🪙 获得金币：{coins}\n"
                f"💰 当前金币：{user_data['coins']}"
            )

    async def _show_shop(self, event):
        """显示商城"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        # 检查用户是否在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候不能购买商品哦！")
            return

        # 显示商城信息
        shop_text = self.shop.get_shop_text(user_data.get('coins', 0))
        yield event.plain_result(shop_text)

    async def _process_purchase(self, event, item_id):
        """处理购买请求"""
        # 直接使用商城模块处理购买
        async for result in self.shop.process_purchase(event, item_id):
            yield result

    async def _compare(self, event):
        """比划功能"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 检查用户是否在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候要认真哦！")
            return

        # 获取自身数据
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result(self.niuniu_texts['dajiao']['not_registered'].format(nickname=nickname))
            return

        # 解析目标
        target_id = self.parse_target(event)
        if not target_id:
            yield event.plain_result(self.niuniu_texts['compare']['no_target'].format(nickname=nickname))
            return
        
        if target_id == user_id:
            yield event.plain_result(self.niuniu_texts['compare']['self_compare'])
            return

        # 获取目标数据
        target_data = self.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result(self.niuniu_texts['compare']['target_not_registered'])
            return

        # 冷却检查
        compare_records = self.last_compare_time.setdefault(group_id, {}).setdefault(user_id, {})
        last_compare = compare_records.get(target_id, 0)
        on_cooldown, remaining = self.check_cooldown(last_compare, self.COMPARE_COOLDOWN)
        if on_cooldown:
            mins = int(remaining // 60) + 1
            text = self.niuniu_texts['compare']['cooldown'].format(
                nickname=nickname,
                remaining=mins
            )
            yield event.plain_result(text)
            return

        # 检查3分钟内比划次数
        compare_records = self.last_compare_time.setdefault(group_id, {}).setdefault(user_id, {})
        last_compare_time = compare_records.get('last_time', 0)
        current_time = time.time()

        # 如果超过3分钟，重置计数
        if current_time - last_compare_time > 180:
            compare_records['count'] = 0
            compare_records['last_time'] = current_time  # 更新最后比划时间

        compare_count = compare_records.get('count', 0)

        if compare_count >= 3:
            yield event.plain_result("❌ 3分钟内只能比划三次")
            return

        # 更新冷却时间和比划次数
        compare_records[target_id] = current_time
        compare_records['count'] = compare_count + 1

        # 检查目标是否有贞操锁
        if self.shop.has_chastity_lock(group_id, target_id):
            time_left = self.shop.get_chastity_lock_time_left(group_id, target_id)
            yield event.plain_result(f"❌ {target_data['nickname']}装备了贞操锁，无法被比划\n剩余时间: {time_left}")
            return

        # 添加变性状态检查
        if self.shop.is_gender_surgery_active(group_id, user_id):
            yield event.plain_result(f"❌ {nickname}，变性状态下牛牛无法变长哦~")
            return

        # 计算胜负
        u_len = user_data['length']
        t_len = target_data['length']
        u_hardness = user_data['hardness']
        t_hardness = target_data['hardness']

        # 基础胜率
        base_win = 0.5

        # 长度影响（最多影响20%的胜率）
        length_factor = (u_len - t_len) / max(u_len, t_len) * 0.2

        # 硬度影响（最多影响10%的胜率）
        hardness_factor = (u_hardness - t_hardness) * 0.05

        # 最终胜率（限制在20%-80%之间）
        win_prob = min(max(base_win + length_factor + hardness_factor, 0.2), 0.8)

        # 记录比划前的长度（移到六味地黄丸判断之前）
        old_u_len = user_data['length']
        old_t_len = target_data['length']

        items = user_data.get('items', {})
        if items.get('pills', False):
            win_prob = 1.0  # 必胜
            items['pills'] = False  # 使用后消失
            
            # 计算胜利效果
            gain = random.randint(0, 3)
            loss = random.randint(1, 2)
            user_data['length'] += gain
            target_data['length'] = max(1, target_data['length'] - loss)
            text = random.choice(self.niuniu_texts['compare']['win']).format(
                nickname=nickname,
                target_nickname=target_data['nickname'],
                gain=gain
            )
            text = f"💊 六味地黄丸生效！必胜！\n{text}"
            
            # 更新数据和继续处理
            if random.random() < 0.3:
                user_data['hardness'] = max(1, user_data['hardness'] - 1)
            if random.random() < 0.3:
                target_data['hardness'] = max(1, target_data['hardness'] - 1)
                
            self._save_niuniu_lengths()
            
            # 生成结果消息
            result_msg = [
                "⚔️ 【牛牛对决结果】 ⚔️",
                f"🗡️ {nickname}: {self.format_length(old_u_len)} > {self.format_length(user_data['length'])}",
                f"🛡️ {target_data['nickname']}: {self.format_length(old_t_len)} > {self.format_length(target_data['length'])}",
                f"📢 {text}"
            ]
            
            yield event.plain_result("\n".join(result_msg))
            return

        # 原有的比划逻辑
        # 记录比划前的长度
        old_u_len = user_data['length']
        old_t_len = target_data['length']

        # 执行判定
        if random.random() < win_prob:
            gain = random.randint(0, 3)
            loss = random.randint(1, 2)
            user_data['length'] += gain
            target_data['length'] = max(1, target_data['length'] - loss)
            text = random.choice(self.niuniu_texts['compare']['win']).format(
                nickname=nickname,
                target_nickname=target_data['nickname'],
                gain=gain
            )
            total_gain = gain
            if (u_len - t_len) <= -20 and user_data['hardness'] < target_data['hardness']:
                # 修正判断：用户长度比对方小20cm以上为极大劣势
                extra_gain = random.randint(0, 5)  # 额外的奖励值
                user_data['length'] += extra_gain
                total_gain += extra_gain
                text += f"\n🎁 由于极大劣势获胜，额外增加 {extra_gain}cm！"
            if abs(u_len - t_len) > 10 and u_len < t_len:
                stolen_length = int(target_data['length'] * 0.2)
                user_data['length'] += stolen_length
                total_gain += stolen_length
                target_data['length'] = max(1, target_data['length'] - stolen_length)
                text += f"\n🎉 {nickname} 战胜了 {target_data['nickname']}，掠夺了 {stolen_length}cm 的长度！"
            if abs(u_len - t_len) <= 5 and user_data['hardness'] > target_data['hardness']:
                text += f"\n🎉 {nickname} 因硬度优势获胜！"
            if total_gain == 0:
                text += f"\n{self.niuniu_texts['compare']['user_no_increase'].format(nickname=nickname)}"
        else:
            gain = random.randint(0, 3)
            loss = random.randint(1, 2)
            target_data['length'] += gain
            user_data['length'] = max(1, user_data['length'] - loss)
            text = random.choice(self.niuniu_texts['compare']['lose']).format(
                nickname=nickname,
                target_nickname=target_data['nickname'],
                loss=loss
            )
            if (u_len - t_len) >= 20 and user_data['hardness'] > target_data['hardness']:
                # 修正判断：用户长度比对方大20cm以上为极大优势
                extra_loss = random.randint(2, 6)  # 具体的惩罚值
                user_data['length'] = max(1, user_data['length'] - extra_loss)
                text += f"\n💔 由于极大优势失败，额外减少 {extra_loss}cm！"
            if abs(u_len - t_len) <= 5 and user_data['hardness'] < target_data['hardness']:
                text += f"\n💔 {nickname} 因硬度劣势败北！"

        # 硬度衰减
        if random.random() < 0.3:
            user_data['hardness'] = max(1, user_data['hardness'] - 1)
        if random.random() < 0.3:
            target_data['hardness'] = max(1, target_data['hardness'] - 1)

        self._save_niuniu_lengths()

        # 生成结果消息
        result_msg = [
            "⚔️ 【牛牛对决结果】 ⚔️",
            f"🗡️ {nickname}: {self.format_length(old_u_len)} > {self.format_length(user_data['length'])}",
            f"🛡️ {target_data['nickname']}: {self.format_length(old_t_len)} > {self.format_length(target_data['length'])}",
            f"📢 {text}"
        ]

        # 添加特殊事件
        special_event_triggered = False

        if abs(u_len - t_len) <= 5 and random.random() < 0.075:
            result_msg.append("💥 双方势均力敌！")
            special_event_triggered = True

        if not special_event_triggered and (user_data['hardness'] <= 2 or target_data['hardness'] <= 2) and random.random() < 0.05:
            result_msg.append("💢 双方牛牛因过于柔软发生缠绕，长度减半！")
            user_data['length'] = max(1, user_data['length'] // 2)
            target_data['length'] = max(1, target_data['length'] // 2)
            special_event_triggered = True

        if not special_event_triggered and abs(u_len - t_len) < 10 and random.random() < 0.025:
            result_msg.append(self.niuniu_texts['compare']['double_loss'].format(nickname1=nickname, nickname2=target_data['nickname']))
            user_data['length'] = max(1, user_data['length'] // 2)
            target_data['length'] = max(1, target_data['length'] // 2)
            special_event_triggered = True

        self._save_niuniu_lengths()

        yield event.plain_result("\n".join(result_msg))

    async def _show_status(self, event):
        """查看牛牛状态"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result(self.niuniu_texts['my_niuniu']['not_registered'].format(nickname=nickname))
            return

        # 检查是否处于变性状态
        is_gender_surgery_active = self.shop.is_gender_surgery_active(group_id, user_id)
        niuniu_name = "洞洞" if is_gender_surgery_active else "牛牛"

        # 评价系统
        length = user_data['length']
        hardness = user_data.get('hardness', 1)  # 获取硬度，默认为1
        length_str = self.format_length(length)
        
        # 为变性状态添加特殊评价
        if is_gender_surgery_active:
            evaluation = "性转成功，变身可爱小萝莉~"
        elif length < 12:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['short'])
        elif length < 25:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['medium'])
        elif length < 50:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['long'])
        elif length < 100:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['very_long'])
        elif length < 200:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['super_long'])
        else:
            evaluation = random.choice(self.niuniu_texts['my_niuniu']['evaluation']['ultra_long'])

        # 修改显示文本，使用正确的称呼
        text = f"📊 {nickname} 的{niuniu_name}状态\n📏 长度：{length_str}\n"
        
        # 只有非变性状态才显示硬度
        if not is_gender_surgery_active:
            text += f"💪 硬度：{hardness}\n"
        else:
            # 如果是变性状态，显示洞洞深度和原牛牛长度
            hole_depth = self.shop.get_hole_depth(group_id, user_id)
            original_length = user_data['gender_surgery'].get('original_length', 0)
            text += f"🕳️ 洞洞深度：{hole_depth}cm\n"
            text += f"📏 原牛牛长度：{self.format_length(original_length)}\n"
        
        text += f"📝 评价：{evaluation}"
        
        # 如果在变性状态，添加剩余时间
        if is_gender_surgery_active:
            time_left = self.shop.get_gender_surgery_time_left(group_id, user_id)
            if time_left:
                text += f"\n⏳ 变性剩余时间：{time_left}"
        
        yield event.plain_result(text)

    async def _show_ranking(self, event):
        """显示排行榜"""
        group_id = str(event.message_obj.group_id)
        group_data = self.get_group_data(group_id)

        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 过滤有效用户数据
        valid_users = [
            (uid, data) for uid, data in group_data.items()
            if isinstance(data, dict) and 'length' in data
        ]

        if not valid_users:
            yield event.plain_result(self.niuniu_texts['ranking']['no_data'])
            return

        # 排序并取前10
        sorted_users = sorted(valid_users, key=lambda x: x[1]['length'], reverse=True)[:10]

        # 构建排行榜
        ranking = [self.niuniu_texts['ranking']['header']]
        for idx, (uid, data) in enumerate(sorted_users, 1):
            ranking.append(
                self.niuniu_texts['ranking']['item'].format(
                    rank=idx,
                    name=data['nickname'],
                    length=self.format_length(data['length'])
                )
            )

        yield event.plain_result("\n".join(ranking))

    async def _show_menu(self, event):
        """显示菜单"""
        menu_text = self.niuniu_texts['menu']['default'] + "\n🏪 牛牛集市 - 交易各种牛牛"
        yield event.plain_result(menu_text)

    async def _lock_niuniu(self, event):
        """锁牛牛功能"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 检查用户是否在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候要认真哦！")
            return

        # 检查自身是否注册
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result(self.niuniu_texts['dajiao']['not_registered'].format(nickname=nickname))
            return

        # 解析目标 - 使用修复后的parse_lock_target
        target_id = self.parse_lock_target(event)
        if not target_id:
            yield event.plain_result(self.niuniu_texts['lock']['no_target'].format(nickname=nickname))
            return
        
        if target_id == user_id:
            yield event.plain_result(self.niuniu_texts['lock']['self_lock'])
            return

        # 获取目标数据
        target_data = self.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result(self.niuniu_texts['lock']['target_not_registered'].format(nickname=nickname))
            return
            
        # 检查目标是否有贞操锁或变性状态
        if self.shop.has_chastity_lock(group_id, target_id):
            time_left = self.shop.get_chastity_lock_time_left(group_id, target_id)
            yield event.plain_result(f"❌ {target_data['nickname']}装备了贞操锁，无法被锁牛牛\n剩余时间: {time_left}")
            return
        
        # 添加变性状态检查
        if self.shop.is_gender_surgery_active(group_id, target_id):
            surgery_time = self.shop.get_gender_surgery_time_left(group_id, target_id)
            yield event.plain_result(f"❌ {target_data['nickname']}正在变性状态下，变成妹子了不能锁哦~\n剩余时间: {surgery_time}")
            return

        # 获取用户的锁定记录
        current_time = time.time()
        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        lock_records = user_actions.setdefault('lock_records', {})
        
        # 检查对特定目标的冷却
        if target_id in lock_records:
            last_lock_time = lock_records[target_id]
            on_cooldown, remaining = self.check_cooldown(last_lock_time, self.LOCK_COOLDOWN)
            if on_cooldown:
                mins = int(remaining // 60) + 1
                text = (f"⚠️ {nickname} 你已经锁过 {target_data['nickname']} 的牛牛了\n"
                       f"🕒 请等待 {mins} 分钟后再次尝试")
                yield event.plain_result(text)
                return

        # 清理5分钟前的记录
        lock_records = {k: v for k, v in lock_records.items() 
                       if current_time - v < 300}  # 300秒 = 5分钟
        
        # 检查5分钟内锁定的不同用户数量
        recent_locks = len(lock_records)
        if recent_locks >= 3 and target_id not in lock_records:
            yield event.plain_result("❌ 5分钟内只能锁3个不同用户的牛牛")
            return

        # 更新锁定记录
        lock_records[target_id] = current_time
        user_actions['lock_records'] = lock_records
        self._save_last_actions()

        # 随机效果判定
        rand = random.random()
        old_length = target_data['length']
        
        if (rand < 0.2):  # 20% 减少
            change = random.randint(1, 5)
            target_data['length'] = max(1, target_data['length'] - change)
            text = self.niuniu_texts['lock']['decrease'].format(
                nickname=nickname,
                target_nickname=target_data['nickname'],
                change=change
            )
        elif (rand < 0.8):  # 60% 增长
            change = random.randint(1, 5)
            target_data['length'] += change
            text = self.niuniu_texts['lock']['increase'].format(
                nickname=nickname,
                target_nickname=target_data['nickname'],
                change=change
            )
        elif (rand < 0.9):  # 10% 咬断
            change = target_data['length'] // 2
            target_data['length'] = max(1, target_data['length'] - change)
            text = self.niuniu_texts['lock']['break'].format(
                nickname=nickname,
                target_nickname=target_data['nickname']
            )
        else:  # 10% 不变
            text = self.niuniu_texts['lock']['no_effect'].format(
                nickname=nickname,
                target_nickname=target_data['nickname']
            )

        self._save_niuniu_lengths()

        # 生成结果消息
        result_msg = [
            "🔒 【锁牛牛结果】 🔒",
            f"👤 {target_data['nickname']}: {self.format_length(old_length)} > {self.format_length(target_data['length'])}",
            f"📢 {text}"
        ]

        yield event.plain_result("\n".join(result_msg))
    # endregion

    async def _view_sign_calendar(self, event):
        """查看签到日历"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        try:
            # 创建签到图片生成器
            sign_generator = SignImageGenerator()
            # 获取用户的签到记录
            sign_records = sign_generator.load_sign_records(user_id, group_id)
            # 生成签到图片
            sign_image_path = sign_generator.create_calendar_image(nickname, user_id, group_id)
            
            # 发送签到图片
            if os.path.exists(sign_image_path):
                yield event.image_result(sign_image_path)
            else:
                yield event.plain_result(f"❌ {nickname}，生成签到日历失败了")
        except Exception as e:
            print(f"生成签到日历失败: {str(e)}")
            yield event.plain_result(f"❌ {nickname}，生成签到日历失败了")

    async def _handle_exchange(self, event):
        """处理牛子转换器调换指令"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        user_data = self.get_user_data(group_id, user_id)
        nickname = event.get_sender_name()
        
        # 检查用户是否等待使用牛子转换器
        if not self.last_actions.get(group_id, {}).get(user_id, {}).get('waiting_for_exchange'):
            yield event.plain_result("❌ 请先购买牛子转换器")
            return
            
        # 解析目标用户
        target_id = self.shop.parse_target(event, "调换")
        if not target_id:
            yield event.plain_result("❌ 请指定有效的目标用户 (@用户 或 输入用户名)")
            return
            
        # 不能对自己使用
        if target_id == user_id:
            yield event.plain_result("❌ 不能与自己交换牛牛")
            return
            
        # 使用转换器
        async for result in self.shop.use_exchanger(event, target_id):
            yield result
            
    async def _handle_lock(self, event):
        """处理锁牛牛指令"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        user_data = self.get_user_data(group_id, user_id)
        nickname = event.get_sender_name()
        
        # 获取目标用户
        target_id = None
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                target_id = str(comp.qq)
                break
                
        if not target_id:
            # 尝试从消息中解析用户名
            msg = event.message_str.strip()
            if msg.startswith("锁牛牛"):
                target_name = msg[3:].strip()
                if target_name:
                    # 在群数据中查找匹配用户名的用户
                    group_data = self.get_group_data(group_id)
                    for uid, udata in group_data.items():
                        if not isinstance(udata, dict):
                            continue
                        if udata.get('nickname', '') and target_name in udata.get('nickname', ''):
                            target_id = uid
                            break
        
        if not target_id:
            yield event.plain_result("❌ 请指定要锁牛牛的用户")
            return
            
        # 检查目标用户是否存在
        target_data = self.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result("❌ 目标用户未注册牛牛")
            return
            
        # 不能锁自己
        if target_id == user_id:
            yield event.plain_result("❌ 不能锁自己的牛牛")
            return
            
        # 检查目标是否有贞操锁
        if self.shop.has_chastity_lock(group_id, target_id):
            yield event.plain_result(f"❌ {target_data['nickname']}装备了贞操锁，无法被锁牛牛")
            return
            
        # 检查冷却时间
        current_time = time.time()
        last_lock = self.last_actions.get(group_id, {}).get(user_id, {}).get('lock', 0)
        if current_time - last_lock < self.LOCK_COOLDOWN:
            remaining = int(self.LOCK_COOLDOWN - (current_time - last_lock))
            yield event.plain_result(f"❌ 锁牛牛冷却中，还需等待{remaining}秒")
            return
            
        # 检查目标是否被锁
        if 'locked_until' in target_data and target_data['locked_until'] > current_time:
            remaining = int(target_data['locked_until'] - current_time)
            yield event.plain_result(f"❌ 该用户已被锁，还剩{remaining}秒")
            return
            
        # 执行锁牛牛
        lock_time = 60 * 10  # 锁10分钟
        target_data['locked_until'] = current_time + lock_time
        target_data['locked_by'] = user_id
        
        # 记录使用时间
        self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})['lock'] = current_time
        
        # 保存数据
        self._save_niuniu_lengths()
        self._save_last_actions()
        
        result = (
            f"🔒 {nickname} 成功锁住了 {target_data['nickname']} 的牛牛！\n"
            f"锁定时间：10分钟"
        )
        yield event.plain_result(result)
        
    async def _handle_dajiao(self, event):
        """处理打胶指令"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        user_data = self.get_user_data(group_id, user_id)
        nickname = event.get_sender_name()
        

        # 检查是否拥有伟哥并使用
        current_time = time.time()
        last_dajiao = self.last_actions.get(group_id, {}).get(user_id, {}).get('dajiao', 0)
        cooldown_passed = current_time - last_dajiao >= self.COOLDOWN_10_MIN
        
        if not cooldown_passed and self.shop.use_viagra_for_dajiao(group_id, user_id):
            # 伟哥效果：无视冷却
            cooldown_passed = True
        
        if not cooldown_passed:
            # 冷却时间未过
            remaining = int(self.COOLDOWN_10_MIN - (current_time - last_dajiao))
            yield event.plain_result(f"❌ 打胶冷却中，还需等待{remaining}秒")
            return
            
        # 剩余的打胶逻辑...

    async def _transfer_coins(self, event):
        """金币转赠功能"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 检查用户是否在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候要认真哦！")
            return

        # 检查自身是否注册
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result(self.niuniu_texts['transfer']['not_registered'])
            return

        # 解析目标用户和金币数量
        msg = event.message_str.strip()
        if msg.startswith("送金币"):
            msg = msg[len("送金币"):].strip()
        
        # 先尝试获取@的用户
        target_id = None
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                target_id = str(comp.qq)
                break
        
        # 如果没有@，尝试从消息中解析用户名
        if not target_id:
            # 尝试从消息中提取用户名和金额
            parts = msg.split()
            if len(parts) < 2:  # 至少需要用户名和金额
                yield event.plain_result(self.niuniu_texts['transfer']['no_target'])
                return
            
            target_name = parts[0]
            # 在群内查找匹配的用户
            for uid, data in group_data.items():
                if isinstance(data, dict) and 'nickname' in data:
                    if target_name in data['nickname']:
                        target_id = uid
                        break
        
        if not target_id:
            yield event.plain_result(self.niuniu_texts['transfer']['no_target'])
            return

        if target_id == user_id:
            yield event.plain_result(self.niuniu_texts['transfer']['self_transfer'])
            return

        # 获取目标数据
        target_data = self.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result(self.niuniu_texts['transfer']['target_not_registered'])
            return

        # 解析金币数量 - 查找最后一个数字
        amounts = []
        for part in msg.split():
            try:
                amount = int(part)
                amounts.append(amount)
            except ValueError:
                continue
        
        if not amounts:
            yield event.plain_result(self.niuniu_texts['transfer']['invalid_amount'])
            return
        
        amount = amounts[-1]  # 使用最后一个数字作为金额
        if amount <= 0:
            yield event.plain_result(self.niuniu_texts['transfer']['invalid_amount'])
            return

        # 检查金币是否足够
        if user_data.get('coins', 0) < amount:
            yield event.plain_result(self.niuniu_texts['transfer']['insufficient_coins'])
            return

        # 执行转赠
        user_data['coins'] -= amount
        target_data['coins'] = target_data.get('coins', 0) + amount
        self._save_niuniu_lengths()

        # 发送成功消息
        text = self.niuniu_texts['transfer']['success'].format(
            amount=amount,
            target_nickname=target_data['nickname'],
            user_balance=user_data['coins'],
            target_balance=target_data['coins']
        )
        yield event.plain_result(text)

    async def _handle_sterilization(self, event):
        """处理绝育指令"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        # 检查插件是否启用
        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 检查用户是否注册
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        # 检查用户是否在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候要认真哦！")
            return

        # 检查是否有待使用的绝育环
        if not self.last_actions.get(group_id, {}).get(user_id, {}).get('waiting_for_sterilization'):
            yield event.plain_result("❌ 请先购买绝育环")
            return

        # 解析目标用户
        target_id = None
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                target_id = str(comp.qq)
                break

        # 如果没有@，尝试从消息中解析用户名
        if not target_id:
            msg = event.message_str.strip()
            if msg.startswith("绝育"):
                target_name = msg[2:].strip()
                if target_name:
                    # 在群数据中查找匹配的用户
                    for uid, data in group_data.items():
                        if isinstance(data, dict) and 'nickname' in data:
                            if target_name in data['nickname']:
                                target_id = uid
                                break

        if not target_id:
            yield event.plain_result("❌ 请指定要绝育的目标用户")
            return

        if target_id == user_id:
            yield event.plain_result("❌ 不能对自己使用绝育环")
            return

        # 使用绝育环
        async for result in self.shop.use_sterilization(event, target_id):
            yield result

    async def _handle_kou_doudou(self, event):
        """处理扣豆指令"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        # 检查插件是否启用
        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 检查用户是否注册
        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        # 检查用户是否在打工中
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候要认真哦！")
            return

        # 解析目标用户
        target_id = None
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                target_id = str(comp.qq)
                break

        # 如果没有@，尝试从消息中解析用户名
        if not target_id:
            msg = event.message_str.strip()
            if msg.startswith("扣"):
                target_name = msg[len("扣"):].strip()
                if target_name:
                    # 在群数据中查找匹配的用户
                    for uid, data in group_data.items():
                        if isinstance(data, dict) and 'nickname' in data:
                            if target_name in data['nickname']:
                                target_id = uid
                                break

        if not target_id:
            yield event.plain_result("❌ 请指定要扣豆的目标用户")
            return

        # 调用shop模块的扣豆方法
        async for result in self.shop.process_kou_doudou(event, target_id):
            yield result

