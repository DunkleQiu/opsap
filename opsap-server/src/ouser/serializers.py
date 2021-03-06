# coding: utf-8
# Author: Dunkle Qiu
from rest_framework import serializers

from .models import User, ExGroup


class UserSerializer(serializers.ModelSerializer):
    groups = serializers.SlugRelatedField('name', many=True, read_only=True)
    mana_group_set = serializers.SlugRelatedField('name', many=True, read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'name', 'role', 'last_login', 'groups', 'mana_group_set')


class ExGroupSerializer(serializers.ModelSerializer):
    user_set = UserSerializer(many=True, read_only=True)
    managers = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = ExGroup
        fields = ('id', 'name', 'comment', 'member_type', 'user_set', 'managers')
