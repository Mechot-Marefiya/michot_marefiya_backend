from django.contrib import admin
from apps.listing.models import TermsAndConditions


@admin.register(TermsAndConditions)
class TermsAndConditionsAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'get_related_object', 'version', 
        'effective_date', 'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'effective_date', 'content_type']
    search_fields = ['version', 'title', 'content']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'effective_date'
    
    fieldsets = (
        ('Related Object', {
            'fields': ('content_type', 'object_id')
        }),
        ('Version Info', {
            'fields': ('version', 'title', 'effective_date', 'is_active')
        }),
        ('Content', {
            'fields': ('content',),
            'classes': ('wide',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
     
    def get_related_object(self, obj):
        return str(obj.content_object) if obj.content_object else f"{obj.content_type}:{obj.object_id}"
    get_related_object.short_description = 'Related To'
    
    def save_model(self, request, obj, form, change):
        # Ensure only one active version per object when saving
        if obj.is_active:
            # Deactivate other versions for same object
            TermsAndConditions.objects.filter(
                content_type=obj.content_type,
                object_id=obj.object_id,
                is_active=True
            ).exclude(id=obj.id).update(is_active=False)
        
        super().save_model(request, obj, form, change)
