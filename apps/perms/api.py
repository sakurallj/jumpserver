# ~*~ coding: utf-8 ~*~
# 

from django.shortcuts import get_object_or_404
from rest_framework.views import APIView, Response
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework import viewsets

from common.utils import set_or_append_attr_bulk
from users.permissions import IsValidUser, IsSuperUser, IsSuperUserOrAppUser
from .utils import AssetPermissionUtil
from .models import AssetPermission
from .hands import AssetGrantedSerializer, User, UserGroup, Asset, Node, \
    NodeGrantedSerializer, SystemUser, NodeSerializer
from . import serializers


class AssetPermissionViewSet(viewsets.ModelViewSet):
    """
    资产授权列表的增删改查api
    """
    queryset = AssetPermission.objects.all()
    serializer_class = serializers.AssetPermissionCreateUpdateSerializer
    permission_classes = (IsSuperUser,)

    def get_serializer_class(self):
        if self.action in ("list", 'retrieve'):
            return serializers.AssetPermissionListSerializer
        return self.serializer_class

    def get_queryset(self):
        queryset = super().get_queryset()
        asset_id = self.request.query_params.get('asset')
        node_id = self.request.query_params.get('node')
        inherit_nodes = set()
        if not asset_id and not node_id:
            return queryset

        permissions = set()
        if asset_id:
            asset = get_object_or_404(Asset, pk=asset_id)
            permissions = set(queryset.filter(assets=asset))
            for node in asset.nodes.all():
                inherit_nodes.update(set(node.ancestor_with_node))
        elif node_id:
            node = get_object_or_404(Node, pk=node_id)
            permissions = set(queryset.filter(nodes=node))
            inherit_nodes = node.ancestor

        for n in inherit_nodes:
            _permissions = queryset.filter(nodes=n)
            set_or_append_attr_bulk(_permissions, "inherit", n.value)
            permissions.update(_permissions)
        return permissions


class UserGrantedAssetsApi(ListAPIView):
    """
    用户授权的所有资产
    """
    permission_classes = (IsSuperUserOrAppUser,)
    serializer_class = AssetGrantedSerializer

    def get_queryset(self):
        user_id = self.kwargs.get('pk', '')
        queryset = []

        if user_id:
            user = get_object_or_404(User, id=user_id)
        else:
            user = self.request.user

        for k, v in AssetPermissionUtil.get_user_assets(user).items():
            if k.is_unixlike():
                system_users_granted = [s for s in v if s.protocol == 'ssh']
            else:
                system_users_granted = [s for s in v if s.protocol == 'rdp']
            k.system_users_granted = system_users_granted
            queryset.append(k)
        return queryset

    def get_permissions(self):
        if self.kwargs.get('pk') is None:
            self.permission_classes = (IsValidUser,)
        return super().get_permissions()


class UserGrantedNodesApi(ListAPIView):
    permission_classes = (IsSuperUser,)
    serializer_class = NodeSerializer

    def get_queryset(self):
        user_id = self.kwargs.get('pk', '')
        if user_id:
            user = get_object_or_404(User, id=user_id)
        else:
            user = self.request.user
        nodes = AssetPermissionUtil.get_user_nodes_with_assets(user)
        return nodes.keys()


class UserGrantedNodesWithAssetsApi(ListAPIView):
    """
    授权用户的资产组，注：这里的资产组并非是授权列表中授权的，
    而是把所有资产取出来，然后反查出所有节点，然后合并得到，
    结果里也包含资产组下授权的资产
    数据结构如下：
    [
      {
        "id": 1,
        "value": "node",
        ... 其它属性
        "assets_granted": [
          {
            "id": 1,
            "hostname": "testserver",
            "ip": "192.168.1.1",
            "port": 22,
            "system_users_granted": [
              "id": 1,
              "name": "web",
              "username": "web",
              "protocol": "ssh",
            ]
          }
        ]
      }
    ]
    """
    permission_classes = (IsSuperUserOrAppUser,)
    serializer_class = NodeGrantedSerializer

    def get_queryset(self):
        user_id = self.kwargs.get('pk', '')
        queryset = []
        if not user_id:
            user = self.request.user
        else:
            user = get_object_or_404(User, id=user_id)

        nodes = AssetPermissionUtil.get_user_nodes_with_assets(user)
        for node, _assets in nodes.items():
            assets = _assets.keys()
            for asset, system_users in _assets.items():
                asset.system_users_granted = system_users
            node.assets_granted = assets
            queryset.append(node)
        return queryset

    def get_permissions(self):
        if self.kwargs.get('pk') is None:
            self.permission_classes = (IsValidUser,)
        return super().get_permissions()


class UserGrantedNodeAssetsApi(ListAPIView):
    permission_classes = (IsSuperUserOrAppUser,)
    serializer_class = AssetGrantedSerializer

    def get_queryset(self):
        user_id = self.kwargs.get('pk', '')
        node_id = self.kwargs.get('node_id')

        if user_id:
            user = get_object_or_404(User, id=user_id)
        else:
            user = self.request.user
        node = get_object_or_404(Node, id=node_id)
        nodes = AssetPermissionUtil.get_user_nodes_with_assets(user)
        assets = nodes.get(node, [])
        for asset, system_users in assets.items():
            asset.system_users_granted = system_users
        return assets


class UserGroupGrantedAssetsApi(ListAPIView):
    permission_classes = (IsSuperUser,)
    serializer_class = AssetGrantedSerializer

    def get_queryset(self):
        user_group_id = self.kwargs.get('pk', '')
        queryset = []

        if not user_group_id:
            return queryset

        user_group = get_object_or_404(UserGroup, id=user_group_id)
        assets = AssetPermissionUtil.get_user_group_assets(user_group)
        for k, v in assets.items():
            k.system_users_granted = v
            queryset.append(k)
        return queryset


class UserGroupGrantedNodesApi(ListAPIView):
    permission_classes = (IsSuperUser,)
    serializer_class = NodeSerializer

    def get_queryset(self):
        group_id = self.kwargs.get('pk', '')
        queryset = []

        if group_id:
            group = get_object_or_404(UserGroup, id=group_id)
            nodes = AssetPermissionUtil.get_user_group_nodes_with_assets(group)
            return nodes.keys()
        return queryset


class UserGroupGrantedNodesWithAssetsApi(ListAPIView):
    permission_classes = (IsSuperUser,)
    serializer_class = NodeGrantedSerializer

    def get_queryset(self):
        user_group_id = self.kwargs.get('pk', '')
        queryset = []

        if not user_group_id:
            return queryset

        user_group = get_object_or_404(UserGroup, id=user_group_id)
        nodes = AssetPermissionUtil.get_user_group_nodes_with_assets(user_group)
        for node, _assets in nodes.items():
            assets = _assets.keys()
            for asset, system_users in _assets.items():
                asset.system_users_granted = system_users
            node.assets_granted = assets
            queryset.append(node)
        return queryset


class UserGroupGrantedNodeAssetsApi(ListAPIView):
    permission_classes = (IsSuperUserOrAppUser,)
    serializer_class = AssetGrantedSerializer

    def get_queryset(self):
        user_group_id = self.kwargs.get('pk', '')
        node_id = self.kwargs.get('node_id')

        user_group = get_object_or_404(UserGroup, id=user_group_id)
        node = get_object_or_404(Node, id=node_id)
        nodes = AssetPermissionUtil.get_user_group_nodes_with_assets(user_group)
        assets = nodes.get(node, [])
        for asset, system_users in assets.items():
            asset.system_users_granted = system_users
        return assets


class ValidateUserAssetPermissionView(APIView):
    permission_classes = (IsSuperUserOrAppUser,)

    @staticmethod
    def get(request):
        user_id = request.query_params.get('user_id', '')
        asset_id = request.query_params.get('asset_id', '')
        system_id = request.query_params.get('system_user_id', '')

        user = get_object_or_404(User, id=user_id)
        asset = get_object_or_404(Asset, id=asset_id)
        system_user = get_object_or_404(SystemUser, id=system_id)

        assets_granted = AssetPermissionUtil.get_user_assets(user)
        if system_user in assets_granted.get(asset, []):
            return Response({'msg': True}, status=200)
        else:
            return Response({'msg': False}, status=403)