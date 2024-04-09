# Generated by Django 5.0.3 on 2024-04-09 12:26

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('document', '0005_alter_document_title'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='documentlibrary',
            name='error',
            field=models.JSONField(null=True),
        ),
        migrations.AddField(
            model_name='documentlibrary',
            name='filename',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='documentlibrary',
            name='object_path',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='documentlibrary',
            name='task_id',
            field=models.CharField(blank=True, max_length=36, null=True),
        ),
        migrations.AddField(
            model_name='documentlibrary',
            name='task_status',
            field=models.CharField(blank=True, db_index=True, default='pending', max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name='documentlibrary',
            name='document',
            field=models.ForeignKey(db_column='document_id', db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='doc_lib', to='document.document'),
        ),
        migrations.CreateModel(
            name='DocumentLibraryFolder',
            fields=[
                ('id', models.CharField(default=uuid.uuid4, max_length=36, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('del_flag', models.BooleanField(db_default=False, default=False)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('user', models.ForeignKey(db_column='user_id', db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'document_library_folder',
                'db_table': 'document_library_folder',
            },
        ),
        migrations.AddField(
            model_name='documentlibrary',
            name='folder',
            field=models.ForeignKey(db_column='folder_id', db_constraint=False, default=None, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='doc_lib_folder', to='document.documentlibraryfolder'),
        ),
    ]
