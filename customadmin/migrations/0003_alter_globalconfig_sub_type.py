# Generated by Django 5.0.3 on 2024-07-16 10:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customadmin', '0002_alter_globalconfig_sub_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='globalconfig',
            name='sub_type',
            field=models.CharField(choices=[('limit', 'limit'), ('exchange', 'exchange'), ('subscribed_bot', 'subscribed_bot'), ('invite_register', 'invite_register'), ('new_user_award', 'new_user_award'), ('duration_award', 'duration_award'), ('discount', 'discount')], db_default=None, default=None, max_length=128, null=True),
        ),
    ]
