from rest_framework.viewsets import ModelViewSet


class AbstractModelViewSet(ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'delete']
