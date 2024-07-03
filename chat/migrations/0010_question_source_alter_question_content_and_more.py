# Generated by Django 5.0.3 on 2024-06-17 07:25

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0009_conversation_is_api'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='source',
            field=models.CharField(blank=True, db_default=None, default=None, max_length=512, null=True),
        ),
        migrations.AlterField(
            model_name='question',
            name='content',
            field=models.TextField(null=True),
        ),
        migrations.CreateModel(
            name='ConversationShare',
            fields=[
                ('id', models.CharField(default=uuid.uuid4, max_length=36, primary_key=True, serialize=False)),
                ('title', models.CharField(blank=True, db_default=None, default=None, max_length=200, null=True)),
                ('bot_id', models.CharField(blank=True, db_default=None, default=None, max_length=36, null=True)),
                ('collections', models.JSONField(null=True)),
                ('documents', models.JSONField(null=True)),
                ('model', models.CharField(blank=True, db_default=None, default=None, max_length=64, null=True)),
                ('content', models.JSONField(blank=True, db_default=None, null=True)),
                ('num', models.IntegerField(db_default=None, default=None, null=True)),
                ('del_flag', models.BooleanField(db_default=False, default=False)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('conversation', models.ForeignKey(db_column='conversation_id', db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='chat.conversation')),
                ('user', models.ForeignKey(db_column='user_id', db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'conversation_share',
                'db_table': 'conversation_share',
            },
        ),
        migrations.AddField(
            model_name='conversation',
            name='share',
            field=models.ForeignKey(db_column='share_id', db_constraint=False, db_default=None, default=None, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='share_conversations', to='chat.conversationshare'),
        ),
    ]