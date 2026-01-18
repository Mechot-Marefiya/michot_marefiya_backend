from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers
from apps.listing.serializers import SearchResultSerializer


search_schema = extend_schema(
    summary="Search available stays",
    description="Returns a list of hotels that have availability for the given date range and number of guests.",
    parameters=[
        OpenApiParameter(
            name="city",
            description="City where the user wants to stay",
            required=True,
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            name="check_in_date",
            description="Check-in date (YYYY-MM-DD)",
            required=True,
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            name="check_out_date",
            description="Check-out date (YYYY-MM-DD)",
            required=True,
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY
        ),
        OpenApiParameter(
            name="guests",
            description="Number of guests",
            required=True,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY
        ),
    ],
    responses={
        200: inline_serializer(
            name='PaginatedStaySearchResponse',
            fields={
                'count': serializers.IntegerField(),
                'next': serializers.URLField(allow_null=True),
                'previous': serializers.URLField(allow_null=True),
                'results': SearchResultSerializer(many=True)
            }
        ),
        400: OpenApiTypes.OBJECT,
    }
)
