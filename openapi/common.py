from drf_spectacular.extensions import OpenApiAuthenticationExtension


class MyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'core.utils.authentication.MyAuthentication'  # full import path OR class ref
    name = 'OpenApiAuthentication'  # name used in the schema

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "OpenAPI-Key",
            "description": "Value should be formatted: `<key>`"
        }