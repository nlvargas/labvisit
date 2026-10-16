from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ["created_at", "direction", "kind", "payload"]
    readonly_fields = fields


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["phone", "lab", "state", "order", "updated_at"]
    list_filter = ["lab", "state"]
    inlines = [MessageInline]
