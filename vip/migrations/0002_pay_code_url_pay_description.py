# Generated by Django 5.0.3 on 2024-07-09 05:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vip', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='pay',
            name='code_url',
            field=models.CharField(db_default=None, default=None, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name='pay',
            name='description',
            field=models.CharField(db_default=None, default=None, max_length=128, null=True),
        ),
    ]
