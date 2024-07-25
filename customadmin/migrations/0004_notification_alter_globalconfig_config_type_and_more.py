# Generated by Django 5.0.3 on 2024-07-25 11:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customadmin', '0003_alter_globalconfig_sub_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, max_length=512, null=True)),
                ('en_title', models.CharField(blank=True, max_length=512, null=True)),
                ('content', models.TextField(blank=True, null=True)),
                ('en_content', models.TextField(blank=True, null=True)),
                ('is_active', models.BooleanField(db_default=False, default=False)),
                ('updated_by', models.CharField(db_default=None, default=None, max_length=36, null=True)),
                ('del_flag', models.BooleanField(db_default=False, default=False)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
            ],
            options={
                'verbose_name': 'notification',
                'db_table': 'notification',
            },
        ),
        migrations.AlterField(
            model_name='globalconfig',
            name='config_type',
            field=models.CharField(choices=[('member_free', 'member_free'), ('member_standard', 'member_standard'), ('member_premium', 'member_premium'), ('vip', 'vip'), ('award', 'award'), ('activity', 'activity'), ('time_clock', 'time_clock')], db_default=None, default=None, max_length=128, null=True),
        ),
        migrations.AlterField(
            model_name='globalconfig',
            name='sub_type',
            field=models.CharField(choices=[('limit', 'limit'), ('exchange', 'exchange'), ('subscribed_bot', 'subscribed_bot'), ('invite_register', 'invite_register'), ('new_user_award', 'new_user_award'), ('duration_award', 'duration_award'), ('discount', 'discount'), ('member', 'member')], db_default=None, default=None, max_length=128, null=True),
        ),
    ]
