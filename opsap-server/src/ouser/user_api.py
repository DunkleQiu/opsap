# coding: utf-8

from .models import ExUser,ExGroup
from opsap.api import get_object, URL, bash
from opsap.settings import EMAIL_HOST_USER as MAIL_FROM


def group_add_user(group, user_id=None, username=None):
    """
    用户组中添加用户
    UserGroup Add a user
    """
    if user_id:
        user = get_object(ExUser, id=user_id)
    else:
        user = get_object(ExUser, username=username)

    if user:
        group.user_set.add(user)


def db_add_group(**kwargs):
    """
    add a user group in database
    数据库中添加用户组
    """
    name = kwargs.get('name')
    group = get_object(ExGroup, name=name)
    users = kwargs.pop('users_id')

    if not group:
        group = ExGroup(**kwargs)
        group.save()
        for user_id in users:
            group_add_user(group, user_id)


def group_update_member(group_id, users_id_list):
    """
    user group update member
    用户组更新成员
    """
    group = get_object(ExGroup, id=group_id)
    if group:
        group.user_set.clear()
        for user_id in users_id_list:
            user = get_object(ExUser, id=user_id)
            if isinstance(user, ExUser):
                group.user_set.add(user)



def db_update_user(**kwargs):
    """
    update a user info in database
    数据库更新用户信息
    """
    groups_post = kwargs.pop('groups')
    admin_groups_post = kwargs.pop('admin_groups')
    user_id = kwargs.pop('user_id')
    user = ExUser.objects.filter(id=user_id)
    user_get = ExUser.objects.get(id=user_id)
    if user:
        pwd = kwargs.pop('password')
        user.update(**kwargs)
        if pwd != '':
            user_get.set_password(pwd)
            user_get.save()
    else:
        return None

    group_select = []
    if groups_post:
        for group_id in groups_post:
            group = ExGroup.objects.filter(id=group_id)
            group_select.extend(group)
    user_get.group = group_select


def db_del_user(username):
    """
    delete a user from database
    从数据库中删除用户
    """
    user = get_object(ExUser, username=username)
    if user:
        user.delete()


def user_add_mail(user, kwargs):
    """
    add user send mail
    发送用户添加邮件
    """
    user_role = {'SU': u'超级管理员', 'GA': u'组管理员', 'CU': u'普通用户'}
    mail_title = u'恭喜你的跳板机用户 %s 添加成功 Jumpserver' % user.name
    mail_msg = u"""
    Hi, %s
        您的用户名： %s
        您的权限： %s
        您的web登录密码： %s
        您的ssh密钥文件密码： %s
        密钥下载地址： %s/ouser/key/down/?uuid=%s
        说明： 请登陆后再下载密钥！
    """ % (user.name, user.username, user_role.get(user.role, u'普通用户'),
           kwargs.get('password'), kwargs.get('ssh_key_pwd'), URL, user.uuid)


def server_del_user(username):
    """
    delete a user from jumpserver linux system
    删除系统上的某用户
    """
    bash('userdel -r %s' % username)


def get_display_msg(user, password, ssh_key_pwd, ssh_key_login_need, send_mail_need):
    if send_mail_need:
        msg = u'添加用户 %s 成功！ 用户密码已发送到 %s 邮箱！' % (user.name, user.email)
        return msg

    if ssh_key_login_need:
        msg = u"""
        跳板机地址： %s
        用户名：%s
        密码：%s
        密钥密码：%s
        密钥下载url: %s/ouser/key/down/?uuid=%s
        该账号密码可以登陆web和跳板机。
        """ % (URL, user.username, password, ssh_key_pwd, URL, user.uuid)
    else:
        msg = u"""
        跳板机地址： %s \n
        用户名：%s \n
        密码：%s \n
        该账号密码可以登陆web和跳板机。
        """ % (URL, user.username, password)

    return msg