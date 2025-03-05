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
if current_dir not in sys.path:
    sys.path.append(current_dir)
from sign_image import SignImageGenerator

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
                    "🎉 {winner} 战胜了 {loser}！\n📈 增加 {gain}cm",
                    "🏆 {winner} 的牛牛更胜一筹！+{gain}cm"
                ],
                'lose': [
                    "😭 {loser} 败给 {winner}\n📉 减少 {loss}cm",
                    "💔 {loser} 的牛牛不敌对方！-{loss}cm"
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
🔹 打工 - 赚取金币
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
    niuniu_commands = ["牛牛菜单", "牛牛开", "牛牛关", "注册牛牛", "打胶", "我的牛牛", "比划比划", "牛牛排行", "锁牛牛", "打工", "打工时间", "牛牛日历"]

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """群聊消息处理器"""
        group_id = str(event.message_obj.group_id)
        msg = event.message_str.strip()

        # 添加购买命令的处理
        if msg.startswith("购买"):
            async for result in self._show_shop(event):
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
            yield event.plain_result("❌ 插件未启用")
            return

        user_data = self.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        # 检查是否已在打工
        if self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，你已经在工作中了哦~")
            return

        # 解析打工时长
        msg = event.message_str.strip()
        match = re.search(r'打工\s*(\d+)\s*小时', msg)
        if not match:
            yield event.plain_result("❌ 请输入正确的打工时长，例如：打工 2小时")
            return

        hours = int(match.group(1))
        if hours <= 0:
            yield event.plain_result("❌ 打工时长必须大于0小时")
            return
        if hours > self.MAX_WORK_HOURS:
            yield event.plain_result(f"❌ 单次打工时长不能超过{self.MAX_WORK_HOURS}小时")
            return

        # 检查每日打工时长限制
        daily_work_time = self._get_daily_work_time(group_id, user_id)
        remaining_hours = self.MAX_WORK_HOURS - daily_work_time
        if remaining_hours <= 0:
            yield event.plain_result(f"❌ 今日打工时长已达上限{self.MAX_WORK_HOURS}小时")
            return
        if hours > remaining_hours:
            yield event.plain_result(f"❌ 今日只能再打工{remaining_hours:.1f}小时")
            return

        # 计算预期金币收益
        expected_coins = (hours * 3600 // self.WORK_REWARD_INTERVAL) * self.WORK_REWARD_COINS

        # 记录打工信息到last_actions
        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        user_actions['work_data'] = {
            'start_time': time.time(),
            'duration': hours
        }
        self._save_last_actions()

        # 启动打工奖励计时器
        async def reward_task():
            user_actions = self.last_actions[group_id][user_id]
            work_data = user_actions['work_data']
            end_time = work_data['start_time'] + hours * 3600
            total_coins = 0
            while time.time() < end_time:
                await asyncio.sleep(self.WORK_REWARD_INTERVAL)
                if not self._is_user_working(group_id, user_id):
                    break
                user_data['coins'] = user_data.get('coins', 0) + self.WORK_REWARD_COINS
                total_coins += self.WORK_REWARD_COINS
                self._save_niuniu_lengths()
            
            # 打工结束后发送提醒消息
            mock_message = AstrBotMessage()
            mock_message.type = MessageType.GROUP_MESSAGE
            mock_message.message = [Plain(f"小南娘：{nickname}，你的打工时间结束了，这次一共赚了{total_coins}金币哦~")]
            mock_message.sender = MessageMember(user_id=user_id)
            mock_message.self_id = user_id
            mock_message.session_id = group_id
            mock_message.group_id = group_id
            mock_message.message_str = f"小南娘：{nickname}，你的打工时间结束了，这次一共赚了{total_coins}金币哦~"
            
            mock_event = AstrMessageEvent(
                message_str=mock_message.message_str,
                message_obj=mock_message,
                platform_meta=PlatformMetadata(
                    name="aiocqhttp",
                    description="模拟的aiocqhttp平台"
                ),
                session_id=group_id
            )
            
            # 发送提醒消息
            await self.context.send_message(mock_event)
        
        asyncio.create_task(reward_task())
        yield event.plain_result(f"小南娘：{nickname}又出来yj啦，这次要陪客户{hours}小时，预计可以赚到{expected_coins}金币哦~")

    async def _check_work_time(self, event):
        """查看打工时间"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        group_data = self.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        work_data = user_actions.get('work_data')
        
        if not work_data or not self._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，你现在没有在工作哦~")
            return

        current_time = time.time()
        end_time = work_data['start_time'] + work_data['duration'] * 3600
        remaining_seconds = end_time - current_time

        remaining_hours = int(remaining_seconds // 3600)
        remaining_minutes = int((remaining_seconds % 3600) // 60)

        yield event.plain_result(f"小南娘：{nickname}，客户还要和你快乐{remaining_hours}小时{remaining_minutes}分哦~")

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

    # 在 _dajiao 方法中修改伟哥效果的判断部分
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

        # 获取当前时间(移到前面)
        current_time = time.time()
        
        # 冷却检查
        last_time = self.last_actions.setdefault(group_id, {}).get(user_id, {}).get('dajiao', 0)
        
        items = user_data.get('items', {})
        if items.get('viagra', 0) > 0:
            # 伟哥效果：直接跳过冷却检查,且必定增加双倍长度
            change = random.randint(10, 20)  # 原来的2-5翻倍为10-20
            user_data['length'] += change
            items['viagra'] -= 1
            text = f"💊 伟哥生效！牛牛增加{change}cm！\n还剩{items['viagra']}次效果"
            
            # 更新最后打胶时间
            self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})['dajiao'] = current_time
            self._save_last_actions()
            self._save_niuniu_lengths()
            
            yield event.plain_result(f"{text}\n当前长度：{self.format_length(user_data['length'])}")
            return
        
        # 普通打胶的冷却检查
        on_cooldown, remaining = self.check_cooldown(last_time, self.COOLDOWN_10_MIN)
        if on_cooldown:
            mins = int(remaining // 60) + 1
            text = random.choice(self.niuniu_texts['dajiao']['cooldown']).format(
                nickname=nickname,
                remaining=mins
            )
            yield event.plain_result(text)
            return

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

    # 在 NiuniuPlugin 类中添加签到方法
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
            if os.path.exists(sign_image_path):
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

    # 在 NiuniuPlugin 类中添加商城相关方法
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

        # 检查是否是购买命令
        msg = event.message_str.strip()
        if msg.startswith("购买"):
            # 检查用户是否在打工中
            if self._is_user_working(group_id, user_id):
                yield event.plain_result(f"小南娘：{nickname}，服务的时候不能购买商品哦！")
                return

            try:
                item_id = int(msg[2:].strip())
                if item_id in [1, 2, 3]:
                    async for result in self._process_purchase(event, item_id):
                        yield result
                else:
                    yield event.plain_result("❌ 无效的商品编号")
            except ValueError:
                pass
            return

        # 显示商城信息
        shop_text = (
            "🏪 牛牛商城\n"
            "1️⃣ 伟哥 - 80金币\n"
            "   无视冷却连续打胶5次，且长度不会变短\n"
            "2️⃣ 男科手术 - 100金币\n"
            "   75%概率长度翻倍，25%概率减半并获得50金币补偿\n"
            "3️⃣ 六味地黄丸 - 20金币\n"
            "   下次比划必胜\n"
            f"💰 你的金币：{user_data.get('coins', 0)}\n"
            "🕒 发送\"购买1\"、\"购买2\"或\"购买3\"购买对应道具"
        )
        yield event.plain_result(shop_text)

    async def _process_purchase(self, event, item_id):
        """处理购买请求"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        user_data = self.get_user_data(group_id, user_id)

        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        coins = user_data.get('coins', 0)
        items = user_data.setdefault('items', {'viagra': 0, 'surgery': False, 'pills': False})

        if item_id == 1:  # 伟哥
            if coins < 80:
                yield event.plain_result("❌ 金币不足")
                return
            user_data['coins'] -= 80
            items['viagra'] = 5
            yield event.plain_result("✅ 购买成功！获得5次伟哥效果")

        elif item_id == 2:  # 男科手术
            if coins < 100:
                yield event.plain_result("❌ 金币不足")
                return
            user_data['coins'] -= 100
            if random.random() < 0.75:  # 75%成功率
                user_data['length'] *= 2
                yield event.plain_result(
                    f"🎉 手术成功！牛牛长度翻倍！\n"
                    f"📏 现在长度：{self.format_length(user_data['length'])}"
                )
            else:
                user_data['length'] = max(1, user_data['length'] // 2)
                user_data['coins'] += 50
                yield event.plain_result(
                    f"💔 手术失败！牛牛变短一半..获得50金币补偿\n"
                    f"📏 现在长度：{self.format_length(user_data['length'])}\n"
                    f"💰 现有金币：{user_data['coins']}"
                )

        elif item_id == 3:  # 六味地黄丸
            if coins < 20:
                yield event.plain_result("❌ 金币不足")
                return
            user_data['coins'] -= 20
            items['pills'] = True
            yield event.plain_result("✅ 购买成功！下次比划必胜")

        self._save_niuniu_lengths()
        
    # 在 _compare 方法中添加六味地黄丸效果判断
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
            if abs(u_len - t_len) >= 20 and user_data['hardness'] < target_data['hardness']:
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
            if abs(u_len - t_len) >= 20 and user_data['hardness'] > target_data['hardness']:
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

        # 评价系统
        length = user_data['length']
        length_str = self.format_length(length)
        if length < 12:
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

        text = self.niuniu_texts['my_niuniu']['info'].format(
            nickname=nickname,
            length=length_str,
            evaluation=evaluation
        )
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
        yield event.plain_result(self.niuniu_texts['menu']['default'])

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

        # 解析目标
        target_id = self.parse_target(event)
        if not target_id:
            yield event.plain_result(self.niuniu_texts['lock']['no_target'].format(nickname=nickname))
            return
        
        if target_id == user_id:
            yield event.plain_result(self.niuniu_texts['lock']['self_lock'])
            return

        # 获取目标数据
        target_data = self.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result(self.niuniu_texts['lock']['target_not_registered'])
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
        
        if rand < 0.2:  # 20% 减少
            change = random.randint(1, 5)
            target_data['length'] = max(1, target_data['length'] - change)
            text = self.niuniu_texts['lock']['decrease'].format(
                nickname=nickname,
                target_nickname=target_data['nickname'],
                change=change
            )
        elif rand < 0.8:  # 60% 增长
            change = random.randint(1, 5)
            target_data['length'] += change
            text = self.niuniu_texts['lock']['increase'].format(
                nickname=nickname,
                target_nickname=target_data['nickname'],
                change=change
            )
        elif rand < 0.9:  # 10% 咬断
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
