import asyncio
import time
from astrbot.api.all import At, Plain, MessageChain

class TimerTest:
    """
    简单的定时消息测试模块
    专门用于测试延时消息回复功能
    """
    
    def __init__(self, context):
        """初始化，传入Context以便发送消息"""
        self.context = context
        self.tasks = {}  # 存储任务引用，防止被垃圾回收
        
    async def test_timer(self, event, delay_minutes=1):
        """
        测试定时器功能
        
        参数:
            event: 消息事件
            delay_minutes: 延迟分钟数，默认1分钟
        """
        user_id = event.get_sender_id()
        nickname = event.get_sender_name()
        
        # 获取消息来源，用于后续发送消息
        unified_msg_origin = event.unified_msg_origin
        
        # 返回确认消息
        yield event.plain_result(f"⏱️ {nickname}，我会在{delay_minutes}分钟后回复你！")
        
        # 创建并存储异步任务
        task_id = f"timer_test_{user_id}_{int(time.time())}"
        task = asyncio.create_task(self._send_delayed_message(
            user_id=user_id,
            nickname=nickname,
            unified_msg_origin=unified_msg_origin,
            delay_minutes=delay_minutes
        ))
        self.tasks[task_id] = task
        
        # 设置清理回调
        task.add_done_callback(lambda t: self.tasks.pop(task_id, None))
    
    async def _send_delayed_message(self, user_id, nickname, unified_msg_origin, delay_minutes):
        """异步发送延迟消息"""
        try:
            # 等待指定时间
            await asyncio.sleep(delay_minutes * 60)
            
            # 构建回复消息
            message = MessageChain([
                At(qq=user_id),
                Plain(f" 定时测试：{nickname}，这是你{delay_minutes}分钟前设置的定时消息！")
            ])
            
            # 发送消息
            await self.context.send_message(unified_msg_origin, message)
            
            # 记录日志
            self.context.logger.info(f"已向用户 {user_id} 发送定时测试消息")
            
        except Exception as e:
            self.context.logger.error(f"发送定时消息失败: {e}")
