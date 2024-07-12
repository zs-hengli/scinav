# Generated by Django 5.0.3 on 2024-07-09 05:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customadmin', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='globalconfig',
            name='sub_type',
            field=models.CharField(choices=[('limit', 'limit'), ('exchange', 'exchange'), ('subscribed_bot', 'subscribed_bot'), ('invite_register', 'invite_register'), ('monthly', 'monthly'), ('discount', 'discount')], db_default=None, default=None, max_length=128, null=True),
        ),
    ]
