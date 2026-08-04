from django.contrib import admin
from .models import Attendance, WebAuthnCredential, WebAuthnChallenge

admin.site.register(Attendance)
admin.site.register(WebAuthnCredential)
admin.site.register(WebAuthnChallenge)
