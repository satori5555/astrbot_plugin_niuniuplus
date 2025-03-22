import random
import time
import asyncio
import datetime
from astrbot.api.all import At, Plain, MessageChain

class NiuniuShop:
    """牛牛商城道具功能"""
    
    # 商品定义
    SHOP_ITEMS = {
        1: {"name": "伟哥", "price": 80, "description": "无视冷却连续打胶5次，且长度不会变短"},
        2: {"name": "男科手术", "price": 100, "description": "75%概率长度翻倍，25%概率减半并获得50金币补偿"},
        3: {"name": "六味地黄丸", "price": 20, "description": "下次比划必胜"},
        4: {"name": "绝育环", "price": 150, "description": "使目标用户无法进行打胶，目标可花费150金币使用指令“解锁绝育”解锁"},
        5: {"name": "暂时变性手术", "price": 100, "description": "牛牛变为0cm，24h后恢复，期间打工金币翻倍"},
        6: {"name": "牛子转换器", "price": 500, "description": "可以与目标用户的牛牛长度对调"},
        7: {"name": "春风精灵", "price": 50, "description": "1小时内每次冷却完毕自动打胶并提醒"},
        8: {"name": "贞操锁", "price": 150, "description": "阻止其他用户对你使用道具、比划和锁牛牛，持续1天"}
    }
    
    def __init__(self, niuniu_plugin):
        """初始化，传入NiuniuPlugin实例以便访问其方法和属性"""
        self.plugin = niuniu_plugin
        self.context = niuniu_plugin.context
        self.niuniu_lengths = niuniu_plugin.niuniu_lengths
        self.last_actions = niuniu_plugin.last_actions
        # 存储各种定时任务的引用
        self.tasks = {}
    
    def _save_data(self):
        """保存数据"""
        self.plugin._save_niuniu_lengths()
        self.plugin._save_last_actions()
    
    def get_shop_text(self, user_coins):
        """生成商城文本"""
        shop_text = "🏪 牛牛商城\n"
        
        for item_id, item in self.SHOP_ITEMS.items():
            shop_text += f"{item_id}️⃣ {item['name']} - {item['price']}金币\n   {item['description']}\n"
        
        shop_text += f"💰 你的金币：{user_coins}\n"
        shop_text += "🕒 发送\"购买+编号\"购买对应道具"
        
        return shop_text
    
    async def process_purchase(self, event, item_id):
        """处理购买请求"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        user_data = self.plugin.get_user_data(group_id, user_id)

        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return

        coins = user_data.get('coins', 0)
        
        # 检查道具是否存在
        if item_id not in self.SHOP_ITEMS:
            yield event.plain_result("❌ 无效的商品编号")
            return
        
        item = self.SHOP_ITEMS[item_id]
        
        # 检查金币是否足够
        if coins < item["price"]:
            yield event.plain_result("❌ 金币不足")
            return
            
        # 扣除金币
        user_data['coins'] -= item["price"]
        
        # 确保items字典存在
        if 'items' not in user_data:
            user_data['items'] = {}
            
        # 根据道具ID处理不同道具效果
        handlers = {
            1: self._handle_viagra,
            2: self._handle_surgery,
            3: self._handle_pills,
            4: lambda u_data: self._prepare_sterilization(u_data, group_id, user_id),
            5: lambda u_data: self._handle_gender_surgery(u_data, group_id, user_id, event),
            6: lambda u_data: self._prepare_exchange(u_data, group_id, user_id),
            7: lambda u_data: self._handle_auto_dajiao(u_data, group_id, user_id, event),
            8: lambda u_data: self._handle_chastity_lock(u_data)
        }
        
        result = handlers[item_id](user_data)
        if asyncio.iscoroutine(result):
            result = await result
            
        self._save_data()
        
        if isinstance(result, str):
            yield event.plain_result(result)
        
    def _handle_viagra(self, user_data):
        """伟哥效果处理"""
        items = user_data.setdefault('items', {})
        # 获取当前伟哥次数，不存在则为0
        current_viagra = items.get('viagra', 0)
        # 增加5次伟哥效果而不是覆盖
        items['viagra'] = current_viagra + 5
        return f"✅ 购买成功！获得5次伟哥效果，当前共有{items['viagra']}次"
        
    def _handle_surgery(self, user_data):
        """男科手术效果处理"""
        # 检查用户是否处于变性状态
        group_id = None
        user_id = None
        
        # 尝试从用户数据反向查找group_id和user_id
        for gid, group_data in self.plugin.niuniu_lengths.items():
            if not isinstance(group_data, dict):
                continue
            for uid, data in group_data.items():
                if data is user_data:
                    group_id = gid
                    user_id = uid
                    break
            if group_id:
                break
                
        # 如果找到了用户ID，检查变性状态
        if group_id and user_id and self.is_gender_surgery_active(group_id, user_id):
            return "❌ 变性状态下无法进行男科手术"
            
        # 正常的手术逻辑
        if random.random() < 0.75:  # 75%成功率
            user_data['length'] *= 2
            return f"🎉 手术成功！牛牛长度翻倍！\n" \
                   f"📏 现在长度：{self.plugin.format_length(user_data['length'])}"
        else:
            user_data['length'] = max(1, user_data['length'] // 2)
            user_data['coins'] += 50
            return f"💔 手术失败！牛牛变短一半..获得50金币补偿\n" \
                   f"📏 现在长度：{self.plugin.format_length(user_data['length'])}\n" \
                   f"💰 现有金币：{user_data['coins']}"
                   
    def _handle_pills(self, user_data):
        """六味地黄丸效果处理"""
        items = user_data.setdefault('items', {})
        items['pills'] = True
        return "✅ 购买成功！下次比划必胜"
        
    def _prepare_sterilization(self, user_data, group_id, user_id):
        """绝育环购买后准备"""
        items = user_data.setdefault('items', {})
        items['sterilization_ring'] = True
        self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})['waiting_for_sterilization'] = True
        return "✅ 购买成功！请发送\"绝育 @用户名\"或\"绝育 用户名\"来使用"
        
    def _handle_gender_surgery(self, user_data, group_id, user_id, event):
        """变性手术效果处理"""
        # 保存原始长度和时间
        original_length = user_data['length']
        end_time = datetime.datetime.now() + datetime.timedelta(hours=24)
        
        # 获取之前保存的洞洞深度（如果存在）
        previous_hole_depth = user_data.get('saved_hole_depth', 0)
        
        user_data['gender_surgery'] = {
            'original_length': original_length,
            'end_time': end_time.timestamp(),
            'hole_depth': previous_hole_depth  # 使用之前保存的洞洞深度
        }
        # 设置长度为0
        user_data['length'] = 0
        self._save_data()
        
        # 创建定时任务24小时后恢复
        async def restore_gender():
            # 计算睡眠时间
            sleep_seconds = (end_time - datetime.datetime.now()).total_seconds()
            if sleep_seconds > 0:
                await asyncio.sleep(sleep_seconds)
                
            try:
                user_data = self.plugin.get_user_data(group_id, user_id)
                if user_data and 'gender_surgery' in user_data:
                    original_length = user_data['gender_surgery']['original_length']
                    # 在恢复前保存当前洞洞深度
                    current_hole_depth = user_data['gender_surgery'].get('hole_depth', 0)
                    user_data['saved_hole_depth'] = current_hole_depth
                    
                    user_data['length'] = original_length
                    del user_data['gender_surgery']
                    self._save_data()
                    
                    # 发送恢复消息
                    try:
                        message_chain = MessageChain([
                            At(qq=user_id),
                            Plain(f"\n小南娘：你的洞洞已经变回牛牛了哦，长度为 {self.plugin.format_length(original_length)}")
                        ])
                        await self.context.send_message(event.unified_msg_origin, message_chain)
                    except Exception as e:
                        print(f"发送牛牛恢复消息失败: {str(e)}")
            except Exception as e:
                print(f"恢复牛牛失败: {str(e)}")
                
        task = asyncio.create_task(restore_gender())
        self.tasks[f"gender_surgery_{group_id}_{user_id}"] = task
        
        # 添加现有洞洞深度信息到返回消息
        depth_msg = f"\n🕳️ 继承之前的洞洞深度: {previous_hole_depth}cm" if previous_hole_depth > 0 else ""
        
        return f"✅ 手术成功！你的牛牛变成了洞洞(0cm)，24小时后会恢复为 {self.plugin.format_length(original_length)}{depth_msg}\n" \
               f"💰 期间打工金币翻倍！"
               
    def _prepare_exchange(self, user_data, group_id, user_id):
        """牛子转换器购买准备"""
        items = user_data.setdefault('items', {})
        items['exchanger'] = True
        self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})['waiting_for_exchange'] = True
        return "✅ 购买成功！请发送\"调换 @用户名\"或\"调换 用户名\"来使用"
        
    def _handle_auto_dajiao(self, user_data, group_id, user_id, event):
        """春风精灵效果处理"""
        # 检查用户是否处于变性状态
        if self.is_gender_surgery_active(group_id, user_id):
            return "❌ 变性状态下无法使用春风精灵"
        
        # 记录春风精灵购买时间和到期时间
        user_data.setdefault('items', {})['spring_fairy'] = {
            'start_time': time.time(),
            'end_time': time.time() + 3600  # 1小时后结束
        }
        
        nickname = event.get_sender_name()
        
        # 创建异步任务处理自动打胶
        async def auto_dajiao():
            end_time = time.time() + 3600
            next_check = time.time() + 10  # 开始时10秒后检查
            
            while time.time() < end_time:
                await asyncio.sleep(max(1, next_check - time.time()))
                
                try:
                    # 检查是否仍有效
                    updated_user_data = self.plugin.get_user_data(group_id, user_id)
                    if not updated_user_data or 'spring_fairy' not in updated_user_data.get('items', {}):
                        break
                    
                    # 检查用户是否变性了，如果变性则停止效果
                    if self.is_gender_surgery_active(group_id, user_id):
                        # 移除春风精灵效果
                        if 'spring_fairy' in updated_user_data.get('items', {}):
                            del updated_user_data['items']['spring_fairy']
                            self._save_data()
                            
                            try:
                                message_chain = MessageChain([
                                    At(qq=user_id),
                                    Plain(f"\n🧚 由于你变性了，春风精灵效果已自动结束")
                                ])
                                await self.context.send_message(event.unified_msg_origin, message_chain)
                            except Exception as e:
                                print(f"发送春风精灵效果结束消息失败: {str(e)}")
                        break
                        
                    current_time = time.time()
                    last_dajiao = self.last_actions.get(group_id, {}).get(user_id, {}).get('dajiao', 0)
                    cooldown = self.plugin.COOLDOWN_10_MIN
                    
                    # 如果冷却已完成
                    if current_time - last_dajiao >= cooldown:
                        # 模拟打胶效果
                        change = random.randint(2, 5)  # 固定增加长度
                        updated_user_data['length'] += change
                        self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})['dajiao'] = current_time
                        self._save_data()
                        
                        # 发送提醒消息
                        try:
                            message_chain = MessageChain([
                                At(qq=user_id),
                                Plain(f"\n🧚 春风精灵帮你打胶成功！\n📏 长度增加: +{change}cm\n"
                                      f"💪 当前长度: {self.plugin.format_length(updated_user_data['length'])}")
                            ])
                            await self.context.send_message(event.unified_msg_origin, message_chain)
                        except Exception as e:
                            print(f"发送自动打胶提醒失败: {str(e)}")
                            
                        # 计算下次冷却完成时间
                        next_check = current_time + cooldown
                    else:
                        # 计算下次检查时间
                        next_check = last_dajiao + cooldown
                except Exception as e:
                    print(f"自动打胶出错: {str(e)}")
                    next_check = time.time() + 60  # 出错后1分钟再检查
                    
            # 效果结束时移除春风精灵
            try:
                final_user_data = self.plugin.get_user_data(group_id, user_id)
                if final_user_data and 'spring_fairy' in final_user_data.get('items', {}):
                    del final_user_data['items']['spring_fairy']
                    self._save_data()
                    
                    # 发送效果结束消息
                    try:
                        message_chain = MessageChain([
                            At(qq=user_id),
                            Plain(f"\n🧚 春风精灵效果已结束")
                        ])
                        await self.context.send_message(event.unified_msg_origin, message_chain)
                    except Exception as e:
                        print(f"发送春风精灵效果结束消息失败: {str(e)}")
            except Exception as e:
                print(f"清理春风精灵数据失败: {str(e)}")
                
        task = asyncio.create_task(auto_dajiao())
        self.tasks[f"spring_fairy_{group_id}_{user_id}"] = task
        
        return "✅ 购买成功！春风精灵将在1小时内帮你自动打胶"
        
    def _handle_chastity_lock(self, user_data):
        """贞操锁效果处理"""
        # 使用datetime设置24小时后的结束时间
        end_time = datetime.datetime.now() + datetime.timedelta(days=1)
        
        items = user_data.setdefault('items', {})
        items['chastity_lock'] = {
            'end_time': end_time.timestamp()
        }
        return "✅ 购买成功！你已装备贞操锁，其他用户无法对你使用道具、比划和锁牛牛，持续1天"
    
    # 使用绝育环
    async def use_sterilization(self, event, target_id):
        """使用绝育环"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        user_data = self.plugin.get_user_data(group_id, user_id)
        nickname = event.get_sender_name()
        
        if not user_data or not user_data.get('items', {}).get('sterilization_ring'):
            yield event.plain_result("❌ 你没有绝育环")
            return
            
        # 检查目标是否存在
        target_data = self.plugin.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result("❌ 目标用户未注册牛牛")
            return
            
        # 检查目标是否有贞操锁
        if target_data.get('items', {}).get('chastity_lock'):
            yield event.plain_result(f"❌ {target_data['nickname']}装备了贞操锁，无法被绝育")
            return
            
        # 应用绝育效果
        target_data.setdefault('items', {})['sterilized'] = True
        # 移除使用者的道具
        del user_data['items']['sterilization_ring']
        
        # 清除待绝育状态
        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        if 'waiting_for_sterilization' in user_actions:
            del user_actions['waiting_for_sterilization']
            
        self._save_data()
        
        yield event.plain_result(f"✅ 成功对 {target_data['nickname']} 实施绝育！\n该用户无法进行打胶，需花费150金币解锁")
    
    # 解锁绝育
    async def unlock_sterilization(self, event):
        """解锁自己的绝育状态"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        user_data = self.plugin.get_user_data(group_id, user_id)
        
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return
            
        if not user_data.get('items', {}).get('sterilized'):
            yield event.plain_result("❌ 你没有被绝育，无需解锁")
            return
            
        if user_data.get('coins', 0) < 150:
            yield event.plain_result("❌ 解锁需要150金币")
            return
            
        # 扣费并解锁
        user_data['coins'] -= 150
        del user_data['items']['sterilized']
        self._save_data()
        
        yield event.plain_result("✅ 成功解锁！你可以继续打胶了")
    
    async def use_exchanger(self, event, target_id):
        """使用牛子转换器"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        user_data = self.plugin.get_user_data(group_id, user_id)
        nickname = event.get_sender_name()
        
        if not user_data or not user_data.get('items', {}).get('exchanger'):
            yield event.plain_result("❌ 你没有牛子转换器")
            return
            
        # 检查目标是否存在
        target_data = self.plugin.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result("❌ 目标用户未注册牛牛")
            return
            
        # 检查目标是否有贞操锁
        if target_data.get('items', {}).get('chastity_lock'):
            yield event.plain_result(f"❌ {target_data['nickname']}装备了贞操锁，无法交换牛子")
            return

        # 检查双方是否有人处于变性状态
        if self.is_gender_surgery_active(group_id, target_id):
            yield event.plain_result(f"❌ {target_data['nickname']}正处于变性状态，无法交换牛子")
            return
        
        if self.is_gender_surgery_active(group_id, user_id):
            yield event.plain_result(f"❌ 你正处于变性状态，无法交换牛子")
            return
            
        # 检查自己是否和目标用户相同
        if user_id == target_id:
            yield event.plain_result("❌ 不能与自己交换牛子")
            return
            
        # 交换长度
        user_length = user_data['length']
        target_length = target_data['length']
        
        user_data['length'] = target_length
        target_data['length'] = user_length
        
        # 移除使用者的道具
        del user_data['items']['exchanger']
        
        # 清除待交换状态
        user_actions = self.last_actions.setdefault(group_id, {}).setdefault(user_id, {})
        if 'waiting_for_exchange' in user_actions:
            del user_actions['waiting_for_exchange']
            
        self._save_data()
        
        yield event.plain_result(
            f"✅ 成功与 {target_data['nickname']} 交换了牛牛长度！\n"
            f"你的牛牛现在是: {self.plugin.format_length(user_data['length'])}\n"
            f"{target_data['nickname']}的牛牛现在是: {self.plugin.format_length(target_data['length'])}"
        )
    
    def is_sterilized(self, group_id, user_id):
        """检查用户是否被绝育"""
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data:
            return False
        return user_data.get('items', {}).get('sterilized', False)
    
    def has_chastity_lock(self, group_id, user_id):
        """检查用户是否有贞操锁"""
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data:
            return False
            
        # 获取贞操锁信息
        lock_data = user_data.get('items', {}).get('chastity_lock')
        if not lock_data:
            return False
        
        # 检查是否为旧版本布尔类型
        if isinstance(lock_data, bool):
            # 如果是布尔值True，转换为字典格式
            if lock_data:
                user_data['items']['chastity_lock'] = {
                    'end_time': time.time() + 86400  # 24小时
                }
                self._save_data()
                return True
            else:
                del user_data['items']['chastity_lock']
                self._save_data()
                return False
        
        # 正常字典类型处理
        end_timestamp = lock_data.get('end_time')
        if not end_timestamp:
            return False
            
        if time.time() > end_timestamp:
            # 自动清理过期状态
            del user_data['items']['chastity_lock']
            self._save_data()
            return False
            
        return True
    
    def is_gender_surgery_active(self, group_id, user_id):
        """检查用户是否正在变性状态"""
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data or 'gender_surgery' not in user_data:
            return False
            
        # 检查是否过期
        end_time = user_data['gender_surgery'].get('end_time', 0)
        if time.time() > end_time:
            # 自动清理过期状态并还原长度
            original_length = user_data['gender_surgery']['original_length']
            user_data['length'] = original_length
            del user_data['gender_surgery']
            self._save_data()
            return False
            
        return True
    
    def get_work_multiplier(self, group_id, user_id):
        """获取打工收益倍率"""
        # 变性状态下打工收益翻倍
        return 2 if self.is_gender_surgery_active(group_id, user_id) else 1
    
    def parse_target(self, event, command_prefix):
        """解析用户指令中的目标用户"""
        # 优先检查@
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                return str(comp.qq)
                
        # 如果没有@，尝试解析用户名
        msg = event.message_str.strip()
        if msg.startswith(command_prefix):
            target_name = msg[len(command_prefix):].strip()
            if target_name:
                group_id = str(event.message_obj.group_id)
                group_data = self.plugin.get_group_data(group_id)
                # 遍历查找匹配的用户名
                for user_id, user_data in group_data.items():
                    if not isinstance(user_data, dict):
                        continue
                    nickname = user_data.get('nickname', '')
                    if nickname and target_name in nickname:
                        return user_id
        return None
        
    def use_viagra_for_dajiao(self, group_id, user_id):
        """使用伟哥进行打胶"""
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data or 'items' not in user_data:
            return False
        
        # 检查用户是否有伟哥
        if 'viagra' not in user_data['items'] or user_data['items']['viagra'] <= 0:
            return False
            
        # 消耗一次伟哥次数
        user_data['items']['viagra'] -= 1
        remaining = user_data['items']['viagra']
        
        if remaining <= 0:
            del user_data['items']['viagra']
            
        self._save_data()
        return remaining  # 返回剩余次数

    async def process_purchase_command(self, event):
        """处理购买命令"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()
        
        # 检查插件是否启用
        group_data = self.plugin.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return
            
        # 检查用户是否注册
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return
            
        # 检查用户是否在打工中
        if self.plugin._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候不能购买商品哦！")
            return
            
        # 解析购买的物品ID
        msg = event.message_str.strip()
        # 如果消息长度至少为3且以"购买"开头
        if len(msg) >= 3 and msg.startswith("购买"):
            try:
                item_id = int(msg[2:].strip())
                if item_id in self.SHOP_ITEMS:
                    async for result in self.process_purchase(event, item_id):
                        yield result
                else:
                    yield event.plain_result(f"❌ 无效的商品编号，有效范围是1-{len(self.SHOP_ITEMS)}")
            except ValueError:
                # 如果无法解析为数字，则显示商城
                shop_text = self.get_shop_text(user_data.get('coins', 0))
                yield event.plain_result(shop_text)
        else:
            # 如果消息不是以"购买"开头，则显示商城
            shop_text = self.get_shop_text(user_data.get('coins', 0))
            yield event.plain_result(shop_text)
    
    # 添加获取贞操锁剩余时间的方法
    def get_chastity_lock_time_left(self, group_id, user_id):
        """获取贞操锁剩余时间文本"""
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data or 'items' not in user_data:
            return None
            
        lock_data = user_data['items'].get('chastity_lock')
        if not lock_data:
            return None
            
        end_timestamp = lock_data.get('end_time')
        if not end_timestamp:
            return None
            
        now = datetime.datetime.now()
        end_time = datetime.datetime.fromtimestamp(end_timestamp)
        
        if end_time <= now:
            # 贞操锁已过期，自动移除
            del user_data['items']['chastity_lock']
            self._save_data()
            return None
            
        # 计算剩余时间
        time_left = end_time - now
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        
        if time_left.days > 0:
            return f"{time_left.days}天{hours}小时{minutes}分钟"
        else:
            return f"{hours}小时{minutes}分钟"
    
    def get_gender_surgery_time_left(self, group_id, user_id):
        """获取变性手术剩余时间文本"""
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data or 'gender_surgery' not in user_data:
            return None
            
        end_timestamp = user_data['gender_surgery'].get('end_time')
        if not end_timestamp:
            return None
            
        now = datetime.datetime.now()
        end_time = datetime.datetime.fromtimestamp(end_timestamp)
        
        if end_time <= now:
            return None
            
        # 计算剩余时间
        time_left = end_time - now
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        
        return f"{hours}小时{minutes}分钟"
    
    # 修复监控贞操锁的方法
    async def monitor_chastity_locks(self):
        """监控并清理过期的贞操锁"""
        while True:
            try:
                now = time.time()
                for group_id, group_data in self.plugin.niuniu_lengths.items():
                    if not isinstance(group_data, dict):
                        continue
                        
                    for user_id, user_data in group_data.items():
                        if not isinstance(user_data, dict) or 'items' not in user_data:
                            continue
                            
                        # 检查贞操锁
                        if 'chastity_lock' in user_data['items']:
                            lock_data = user_data['items']['chastity_lock']
                            # 检查lock_data是否为字典类型
                            if not isinstance(lock_data, dict):
                                # 如果不是字典，可能是旧版本的bool类型，修复它
                                user_data['items']['chastity_lock'] = {
                                    'end_time': now + 86400  # 设置24小时后过期
                                }
                                self._save_data()
                                continue

                            end_time = lock_data.get('end_time')
                            
                            if end_time and now > end_time:
                                # 贞操锁过期，移除
                                del user_data['items']['chastity_lock']
                                self._save_data()
                                
                                # 获取用户群和会话信息
                                if 'nickname' in user_data:
                                    nickname = user_data['nickname']
                                    try:
                                        # 构建消息链
                                        message_chain = MessageChain([
                                            At(qq=user_id),
                                            Plain(f" 小南娘：你的贞操锁已经失效了哦~")
                                        ])
                                        # 获取该群的第一个会话ID
                                        for event in self.context.unified_msg_list:
                                            if str(event.message_obj.group_id) == str(group_id):
                                                unified_msg = event.unified_msg_origin
                                                await self.context.send_message(unified_msg, message_chain)
                                                break
                                    except Exception as e:
                                        print(f"发送贞操锁失效提醒失败: {str(e)}")
                
            except Exception as e:
                print(f"监控贞操锁时出错: {str(e)}")
                
            await asyncio.sleep(600)
    
    # 修改变性状态监控方法中的消息
    async def monitor_gender_surgeries(self):
        """监控并处理过期的变性手术"""
        while True:
            try:
                now = time.time()
                for group_id, group_data in self.plugin.niuniu_lengths.items():
                    if not isinstance(group_data, dict):
                        continue
                        
                    for user_id, user_data in group_data.items():
                        if not isinstance(user_data, dict) or 'gender_surgery' not in user_data:
                            continue
                            
                        surgery_data = user_data['gender_surgery']
                        if not isinstance(surgery_data, dict):
                            del user_data['gender_surgery']
                            self._save_data()
                            continue
                            
                        end_time = surgery_data.get('end_time', 0)
                        
                        if end_time and now > end_time:
                            # 变性手术过期，恢复长度
                            original_length = surgery_data.get('original_length', 10)
                            
                            # 保存当前的洞洞深度
                            current_hole_depth = surgery_data.get('hole_depth', 0)
                            user_data['saved_hole_depth'] = current_hole_depth
                            
                            user_data['length'] = original_length
                            del user_data['gender_surgery']
                            self._save_data()
                            
                            try:
                                # 构建消息链
                                message_chain = MessageChain([
                                    At(qq=user_id),
                                    Plain(f"\n小南娘：你的洞洞已经变回牛牛了哦，长度为 {self.plugin.format_length(original_length)}")
                                ])
                                # 获取该群的第一个会话ID
                                for event in self.context.unified_msg_list:
                                    if str(event.message_obj.group_id) == str(group_id):
                                        unified_msg = event.unified_msg_origin
                                        await self.context.send_message(unified_msg, message_chain)
                                        break
                            except Exception as e:
                                print(f"发送变性结束提醒失败: {str(e)}")
                            
            except Exception as e:
                print(f"监控变性手术时出错: {str(e)}")
                
            await asyncio.sleep(600)
    
    # 添加获取春风精灵剩余时间的方法
    def get_spring_fairy_time_left(self, group_id, user_id):
        """获取春风精灵剩余时间文本"""
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data or 'items' not in user_data:
            return None
            
        fairy_data = user_data['items'].get('spring_fairy')
        if not fairy_data:
            return None
            
        end_time = fairy_data.get('end_time')
        if not end_time:
            return None
            
        now = time.time()
        if now >= end_time:
            return None
            
        # 计算剩余时间
        time_left = end_time - now
        minutes = int(time_left // 60)
        seconds = int(time_left % 60)
        
        return f"{minutes}分钟{seconds}秒"
    
    # 添加背包查看功能
    async def show_backpack(self, event):
        """显示用户背包"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()

        # 检查插件是否启用
        group_data = self.plugin.get_group_data(group_id)
        if not group_data.get('plugin_enabled', False):
            yield event.plain_result("❌ 插件未启用")
            return

        # 检查用户是否注册
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data:
            yield event.plain_result("❌ 请先注册牛牛")
            return
            
        # 检查用户是否在打工中
        if self.plugin._is_user_working(group_id, user_id):
            yield event.plain_result(f"小南娘：{nickname}，服务的时候不能查看背包哦！")
            return
            
        # 获取背包内容
        items = user_data.get('items', {})
        if not items:
            yield event.plain_result(f"🎒 {nickname} 的背包是空的")
            return
            
        # 构建背包内容文本
        backpack_text = f"🎒 {nickname} 的牛牛背包\n"
        
        # 处理伟哥
        if 'viagra' in items:
            backpack_text += f"💊 伟哥: 剩余{items['viagra']}次\n"
            
        # 处理六味地黄丸
        if items.get('pills'):
            backpack_text += "🌿 六味地黄丸: 下次比划必胜\n"
            
        # 处理绝育环
        if items.get('sterilization_ring'):
            backpack_text += "⭕ 绝育环: 可使用\n"
            
        # 处理被绝育状态
        if items.get('sterilized'):
            backpack_text += "⛓️ 被绝育: 需花费150金币解锁\n"
            
        # 处理牛子转换器
        if items.get('exchanger'):
            backpack_text += "🔄 牛子转换器: 可使用\n"
            
        # 处理贞操锁
        if 'chastity_lock' in items:
            time_left = self.get_chastity_lock_time_left(group_id, user_id)
            if time_left:
                backpack_text += f"🔒 贞操锁: 剩余{time_left}\n"
            
        # 处理春风精灵
        if 'spring_fairy' in items:
            time_left = self.get_spring_fairy_time_left(group_id, user_id)
            if time_left:
                backpack_text += f"🧚 春风精灵: 剩余{time_left}\n"
                
        # 处理变性手术状态
        if 'gender_surgery' in user_data:
            time_left = self.get_gender_surgery_time_left(group_id, user_id)
            if time_left:
                backpack_text += f"🔄 暂时变性: 剩余{time_left}\n"
        
        yield event.plain_result(backpack_text)
        
    # 新增方法：获取用户当前的牛牛称呼（变性状态下为"洞洞"）
    def get_niuniu_name(self, group_id, user_id):
        """获取用户当前的牛牛称呼，变性状态下为"洞洞"，否则为"牛牛" """
        if self.is_gender_surgery_active(group_id, user_id):
            return "洞洞"
        return "牛牛"
    
    # 添加扣豆功能处理方法
    async def process_kou_doudou(self, event, target_id):
        """处理扣豆功能"""
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        user_data = self.plugin.get_user_data(group_id, user_id)
        nickname = event.get_sender_name()
        
        # 获取目标用户数据
        target_data = self.plugin.get_user_data(group_id, target_id)
        if not target_data:
            yield event.plain_result("❌ 目标用户未注册牛牛")
            return
        
        target_nickname = target_data.get('nickname', '用户')
        
        # 检查目标是否处于变性状态
        if not self.is_gender_surgery_active(group_id, target_id):
            yield event.plain_result(f"❌ {target_nickname}没有变性，不能扣豆！")
            return
        
        # 检查目标是否有贞操锁
        if self.has_chastity_lock(group_id, target_id):
            time_left = self.get_chastity_lock_time_left(group_id, target_id)
            yield event.plain_result(f"❌ {target_nickname}装备了贞操锁，无法被扣豆\n剩余时间: {time_left}")
            return
        
        # 检查是否为自己
        if user_id == target_id:
            yield event.plain_result("❌ 不能自己扣自己")
            return
            
        # 随机减少长度（即洞洞变深）
        depth_increase = random.randint(1, 5)  # 随机减少1-5cm
        
        # 保存用户的变性手术数据
        surgery_data = target_data.get('gender_surgery', {})
        if 'hole_depth' not in surgery_data:
            surgery_data['hole_depth'] = 0
        
        # 增加洞洞深度
        surgery_data['hole_depth'] += depth_increase
        target_data['gender_surgery'] = surgery_data
        self._save_data()
        
        # 显示结果
        yield event.plain_result(f"💦 {target_nickname}被{nickname}扣爽了，洞洞深了{depth_increase}cm！\n现在洞洞深度: {surgery_data['hole_depth']}cm")
    
    # 修改获取变性手术剩余时间的方法，增加显示洞洞深度
    def get_gender_surgery_time_left(self, group_id, user_id):
        """获取变性手术剩余时间文本"""
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data or 'gender_surgery' not in user_data:
            return None
            
        end_timestamp = user_data['gender_surgery'].get('end_time')
        if not end_timestamp:
            return None
            
        now = datetime.datetime.now()
        end_time = datetime.datetime.fromtimestamp(end_timestamp)
        
        if end_time <= now:
            return None
            
        # 计算剩余时间
        time_left = end_time - now
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        
        return f"{hours}小时{minutes}分钟"
    
    # 添加方法获取洞洞深度
    def get_hole_depth(self, group_id, user_id):
        """获取用户洞洞深度"""
        user_data = self.plugin.get_user_data(group_id, user_id)
        if not user_data or 'gender_surgery' not in user_data:
            return 0
            
        return user_data['gender_surgery'].get('hole_depth', 0)
