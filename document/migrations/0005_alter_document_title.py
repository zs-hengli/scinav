# Generated by Django 5.0.3 on 2024-04-07 14:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('document', '0004_remove_document_is_open_access_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='title',
            field=models.CharField(blank=True, db_default=None, db_index=True, default=None, max_length=512, null=True),
        ),
    ]