# Generated by Django 5.0.3 on 2024-05-24 06:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('openapi', '0002_alter_openapikey_api_key_show'),
    ]

    operations = [
        migrations.AlterField(
            model_name='openapilog',
            name='model',
            field=models.CharField(db_default=None, default=None, max_length=256, null=True),
        ),
    ]
