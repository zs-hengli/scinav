from rest_framework.throttling import SimpleRateThrottle


class UserRateThrottle(SimpleRateThrottle):
    scope = 'user_rate'

    def get_ident(self, request):
        user = request.user
        path = request.path
        if user and user.is_authenticated:
            ident = f"{user.id}:{path}"
        else:
            ident = f"{super().get_ident(request)}:{path}"
        return ident

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }