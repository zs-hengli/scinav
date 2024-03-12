# Generated by Django 5.0.3 on 2024-03-12 09:10

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('bot', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.CharField(default=uuid.uuid4, max_length=36, primary_key=True, serialize=False)),
                ('title', models.CharField(blank=True, db_default=None, default=None, max_length=200, null=True)),
                ('type', models.CharField(blank=True, db_default=None, default=None, max_length=32, null=True)),
                ('docs', models.JSONField(null=True)),
                ('model', models.CharField(blank=True, db_default=None, default=None, max_length=64, null=True)),
                ('del_flag', models.BooleanField(db_default=False, default=False)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('bot', models.ForeignKey(db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='conv', to='bot.bot')),
                ('user', models.ForeignKey(db_column='user_id', db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'conversation',
                'db_table': 'conversation',
            },
        ),
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.CharField(default=uuid.uuid4, max_length=36, primary_key=True, serialize=False)),
                ('prompt', models.TextField()),
                ('answer', models.TextField(blank=True, db_default=None, null=True)),
                ('docs', models.JSONField(null=True)),
                ('is_like', models.BooleanField(db_default=None, default=None, null=True)),
                ('del_flag', models.BooleanField(db_default=False, default=False)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('conversation', models.ForeignKey(db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='question', to='chat.conversation')),
            ],
            options={
                'verbose_name': 'question',
                'db_table': 'question',
            },
        ),
    ]
