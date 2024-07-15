from django.urls import path

from . import views

urlpatterns = [
    path('vip/index', views.Index.as_view(), name='index'),
    path('vip/member', views.Members.as_view(), name='member'),

    path('vip/tokens/expire', views.TokensExpire.as_view(), name='tokens_expire'),
    path('vip/exchange', views.Exchange.as_view(), name='exchange'),
    path('vip/trades', views.Trades.as_view(), name='trades'),
    path('vip/trades/<str:status>', views.Trades.as_view(), name='trades'),
    path('vip/award', views.TokensAward.as_view(), name='award'),

    path('pay/qrcode', views.PayQrcode.as_view(), name='pay_qrcode'),
    path('pay/status/<str:out_trade_no>', views.PayStatus.as_view(), name='pay_status'),
    path('pay/notify', views.WeixinNotify.as_view(), name='notify'),
    #
]

"""
接口：
pk vip/member  账户信息
    余额 
    账户类型 剩余天数
    问题使用量
    文件解析量

ok pay/qrcode 获取充值二维码  amount description
    image，code_url


ok vip/tokens/expire 到期代币列表
    balance_amount
    end_date


ok config 配置信息 config_type:member_free,member_standard,member_premium


vip/exchange 兑换会员  member_type（standard, premium） duration:（30,90,360）


orders 订单列表：
    id
    type
    amount
    trade_no
    status in_progress,completed,freezing
    end_date
    remaining_days
    start_date
    tokens
    
定时任务:
    定时清理过期的代币
    判断会员是否到期 修改状态 
    定时check支付状态为NOTPAY的订单
    
赠送代币：
    type: subscribed_bot,invite_register,new_user_award,duration_award
"""
