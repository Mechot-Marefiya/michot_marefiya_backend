from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers
from .models import Favorite


class FavoriteSerializer(serializers.ModelSerializer):
    content_type = serializers.CharField(write_only=True)
    object_id = serializers.CharField()
    content_type_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Favorite
        fields = ("id", "content_type", "object_id", "content_type_display", "created_at")
        read_only_fields = ("id", "created_at", "content_type_display")

    def validate(self, attrs):
        ct_label = attrs.get("content_type")
        try:
            if "." in ct_label:
                app_label, model = ct_label.split(".")
                ct = ContentType.objects.get(app_label=app_label, model=model.lower())
            else:
                ct = ContentType.objects.get(pk=int(ct_label))
        except Exception:
            raise serializers.ValidationError({"content_type": "Invalid content_type"})

        attrs["content_type_obj"] = ct
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        ct = validated_data.pop("content_type_obj")
        object_id = validated_data.get("object_id")

        fav, created = Favorite.objects.get_or_create(
            user=user, content_type=ct, object_id=str(object_id)
        )
        return fav

    def get_content_type_display(self, obj):
        return f"{obj.content_type.app_label}.{obj.content_type.model}"
