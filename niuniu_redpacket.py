import random
import time
import asyncio
import re
from astrbot.api.all import At, Plain, MessageChain

class NiuniuRedPacket:
    """牛牛红包功能类"""
    
    def __init__(self, niuniu_plugin):
        """初始化，传入NiuniuPlugin实例以便访问其方法和属性"""
        self.plugin = niuniu_plugin
        self.context = niuniu_plugin.context
        self.niuniu_lengths = niuniu_plugin.niuniu_lengths
        # 红包数据结构
        self.red_packets = {}  # {group_id: {packet_id: {sender, sender_nickname, amount, count, remaining, remaining_amount, timestamp, participants}}}
        # 存储红包任务
        self.tasks = {}
        
    def _save_data(self):
        """保存用户数据"""
        self.plugin._save_niuniu_lengths()
        
    async def handle_send_red_packet(self, event):
        """处理发红包命令"""
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
            yield event.plain_result(f"小南娘：{nickname}，服务的时候不能发红包哦！")
            return
        
        # 解析红包金额和数量
        msg = event.message_str.strip()
        match = re.search(r'发红包\s*(\d+)\s*(\d+)', msg)
        if not match:
            yield event.plain_result("❌ 格式错误，请使用：发红包 [金额] [个数]")
            return
        
        amount = int(match.group(1))
        count = int(match.group(2))
        
        # 检查参数合法性
        if amount <= 0 or count <= 0:
            yield event.plain_result("❌ 金额和个数必须大于0")
            return
        
        if count > amount:
            yield event.plain_result("❌ 红包个数不能超过红包金额")
            return
        
        # 检查用户金币是否足够
        if user_data.get('coins', 0) < amount:
            yield event.plain_result("❌ 金币不足")
            return
        
        # 扣除用户金币
        user_data['coins'] -= amount
        self._save_data()
        
        # 生成红包ID
        packet_id = f"{int(time.time())}_{user_id}"
        
        # 存储红包信息
        if group_id not in self.red_packets:
            self.red_packets[group_id] = {}
        
        self.red_packets[group_id][packet_id] = {
            'sender': user_id,
            'sender_nickname': nickname,
            'amount': amount,
            'count': count,
            'remaining': count,
            'remaining_amount': amount,
            'timestamp': time.time(),
            'participants': []
        }
        
        # 设置红包过期任务
        unified_msg_origin = event.unified_msg_origin
        task_id = f"red_packet_{group_id}_{packet_id}"
        task = asyncio.create_task(self._red_packet_expiration(
            group_id=group_id,
            packet_id=packet_id,
            unified_msg_origin=unified_msg_origin
        ))
        
        # 存储任务引用
        self.tasks[task_id] = task
        
        # 设置清理回调
        task.add_done_callback(lambda t: self.tasks.pop(task_id, None))
        
        # 发送红包通知
        chain = [
            At(qq=event.get_sender_id()),
            Plain(f"\n🧧 发出了 {amount} 金币的红包，共 {count} 个！\n发送\"抢红包\"即可参与")
        ]
        yield event.chain_result(chain)
        
    async def handle_grab_red_packet(self, event):
        """处理抢红包命令"""
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
            yield event.plain_result(f"小南娘：{nickname}，服务的时候不能抢红包哦！")
            return
        
        # 检查当前群是否有红包
        if group_id not in self.red_packets or not self.red_packets[group_id]:
            yield event.plain_result("❌ 当前没有可抢的红包")
            return
        
        # 获取最新的红包
        packet_id, packet_data = self._get_latest_red_packet(group_id)
        if not packet_id:
            yield event.plain_result("❌ 当前没有可抢的红包")
            return
        
        # 检查用户是否已经抢过这个红包
        if user_id in packet_data['participants']:
            yield event.plain_result("❌ 你已经抢过这个红包了")
            return
        
        # 检查是否是发红包的人自己
        if user_id == packet_data['sender']:
            yield event.plain_result("❌ 不能抢自己的红包")
            return
        
        # 计算获得的金币数量
        amount_received = self._calculate_red_packet_amount(packet_data)
        
        # 更新红包数据
        packet_data['remaining'] -= 1
        packet_data['remaining_amount'] -= amount_received
        packet_data['participants'].append(user_id)
        
        # 更新用户金币
        user_data['coins'] = user_data.get('coins', 0) + amount_received
        self._save_data()
        
        # 发送抢红包成功通知
        chain = [
            At(qq=event.get_sender_id()),
            Plain(f"\n🧧 抢到了 {amount_received} 金币！\n当前红包剩余 {packet_data['remaining']} 个")
        ]
        yield event.chain_result(chain)
        
        # 如果红包已经被抢完，清理红包数据
        if packet_data['remaining'] <= 0:
            # 发送红包被抢完的提示
            sender_chain = [
                At(qq=packet_data['sender']),
                Plain(f"\n🧧 你发的红包已被抢完！")
            ]
            await self.context.send_message(event.unified_msg_origin, MessageChain(sender_chain))
            
            del self.red_packets[group_id][packet_id]
            if not self.red_packets[group_id]:
                del self.red_packets[group_id]
    
    def _get_latest_red_packet(self, group_id):
        """获取群内最新的红包"""
        if group_id not in self.red_packets or not self.red_packets[group_id]:
            return None, None
        
        # 按照发送时间排序，获取最新的红包
        latest_packet_id = max(self.red_packets[group_id].keys(), 
                              key=lambda k: self.red_packets[group_id][k]['timestamp'])
        return latest_packet_id, self.red_packets[group_id][latest_packet_id]
    
    def _calculate_red_packet_amount(self, packet_data):
        """计算抢红包获得的金币数量"""
        remaining = packet_data['remaining']
        remaining_amount = packet_data['remaining_amount']
        
        # 如果只剩下最后一个红包，直接返回剩余全部金额
        if remaining == 1:
            return remaining_amount
        
        # 随机计算金额，确保不为0且不超过剩余金额
        # 使用剩余平均值的2倍作为上限，但不能超过剩余总额减去剩余人数-1
        max_amount = min(remaining_amount - (remaining - 1), int(remaining_amount / remaining * 2))
        if max_amount <= 1:
            return 1
        
        return random.randint(1, max_amount)
        
    async def _red_packet_expiration(self, group_id, packet_id, unified_msg_origin):
        """处理红包过期"""
        try:
            # 等待5分钟
            await asyncio.sleep(300)  # 5分钟 = 300秒
            
            # 检查红包是否仍然存在
            if (group_id in self.red_packets and 
                packet_id in self.red_packets[group_id]):
                
                packet_data = self.red_packets[group_id][packet_id]
                sender_id = packet_data['sender']
                nickname = packet_data['sender_nickname']
                
                # 如果还有剩余红包，返还金额给发送者
                if packet_data['remaining_amount'] > 0:
                    # 获取发送者数据
                    sender_data = self.plugin.get_user_data(group_id, sender_id)
                    if sender_data:
                        # 更新金币
                        sender_data['coins'] = sender_data.get('coins', 0) + packet_data['remaining_amount']
                        self._save_data()
                        
                        # 发送提醒消息
                        try:
                            message_chain = MessageChain([
                                At(qq=sender_id),
                                Plain(f" 小南娘：你的红包已过期，已返还 {packet_data['remaining_amount']} 金币")
                            ])
                            await self.context.send_message(unified_msg_origin, message_chain)
                        except Exception as e:
                            self.context.logger.error(f"发送红包过期提醒失败: {e}")
                
                # 清理红包数据
                del self.red_packets[group_id][packet_id]
                if not self.red_packets[group_id]:
                    del self.red_packets[group_id]
        except Exception as e:
            self.context.logger.error(f"红包过期处理异常: {e}")
