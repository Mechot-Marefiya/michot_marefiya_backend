from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED, HTTP_200_OK
from apps.account.models import User
from apps.account.serializers import UserResponseSerializer, UserSerializer


class UserAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        queryset = User.objects.all()
        serializer = UserResponseSerializer(queryset, many=True)

        return Response(serializer.data, HTTP_200_OK)


class SignupAPIView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=HTTP_201_CREATED)


class UserDetailAPIView(APIView):
    def get(self, request: Request, pk) -> Response:
        queryset = get_object_or_404(User, id=pk)
        serializer = UserResponseSerializer(queryset)

        return Response(serializer.data, status=HTTP_200_OK)

    def patch(self, request: Request, pk) -> Response:
        instance = get_object_or_404(User, id=pk)
        print(instance)
        serializer = UserSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, HTTP_200_OK)
