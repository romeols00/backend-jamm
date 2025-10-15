from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from backend import settings

class UtenteManager(BaseUserManager):
    def create_user(self, email, password=None, tipo=None, **extra_fields):
        if not email:
            raise ValueError("L'email è obbligatoria")
        email = self.normalize_email(email)
        user = self.model(email=email, tipo=tipo, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, tipo='persona', **extra_fields)

class Utente(AbstractBaseUser, PermissionsMixin):
    TIPO_CHOICES = [('persona', 'Persona'), ('locale', 'Locale')]

    email = models.EmailField(unique=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    data_registrazione = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['tipo']

    objects = UtenteManager()

    def __str__(self):
        return self.email

class Persona(models.Model):
    SESSO_CHOICES = [
    ("M", "Maschio"),
    ("F", "Femmina"),
    ("O", "Altro"),
]
    
    utente = models.OneToOneField(Utente, on_delete=models.CASCADE)
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    data_nascita = models.DateField(null=True, blank=True)
    sesso = models.CharField(max_length=1, choices=SESSO_CHOICES, null=True, blank=True)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    situazione_sentimentale = models.CharField( max_length=20, null=True,    blank=True)
    profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True)
    last_lat = models.DecimalField(max_digits=11, decimal_places=7, null=True, blank=True)
    last_lng = models.DecimalField(max_digits=11, decimal_places=7, null=True, blank=True)
    last_accuracy = models.FloatField(null=True, blank=True)
    last_loc_ts = models.DateTimeField(null=True, blank=True)

    hidden_fields = ArrayField(
        base_field=models.CharField(max_length=50),
        default=list,
        blank=True,
        help_text="Campi del profilo che l'utente vuole NASCONDERE"
    )

    def is_public(self, field: str) -> bool:
        # nome/cognome sempre visibili per policy
        if field in ("nome", "cognome"):
            return True
        return field not in (self.hidden_fields or [])

class Locale(models.Model):
    utente = models.OneToOneField(Utente, on_delete=models.CASCADE)
    nome_locale = models.CharField(max_length=150)
    indirizzo = models.TextField()
    partita_iva = models.CharField(max_length=20, null=True, blank=True)
    telefono_contatto = models.CharField(max_length=20, blank=True)

    profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True)

    latitudine = models.FloatField(null=True, blank=True)
    longitudine = models.FloatField(null=True, blank=True)

    hidden_fields = ArrayField(
        base_field=models.CharField(max_length=50),
        default=list,
        blank=True,
        help_text="Campi del profilo che il locale vuole NASCONDERE"
    )

    def __str__(self):
        return self.nome_locale

    def is_public(self, field: str) -> bool:
        return field not in (self.hidden_fields or [])


class Evento(models.Model):
    locale = models.ForeignKey(Locale, on_delete=models.CASCADE)
    titolo = models.CharField(max_length=255)
    descrizione = models.TextField(blank=True,  null=True)
    altre_informazioni = models.TextField(blank=True,  null=True)
    programma = models.TextField(blank=True,  null=True)
    informazioni_utili = models.TextField(blank=True,  null=True)
    data_evento = models.DateField()
    orario_evento = models.TimeField()
    luogo = models.CharField(max_length=255, blank=True,  null=True)
    prezzo = models.DecimalField(max_digits=8, decimal_places=2, blank=True,  null=True)
    posti_disponibili = models.IntegerField(blank=True,  null=True)
    creato_il = models.DateTimeField(auto_now_add=True)
    locandina = models.ImageField(upload_to="locandine/", null=True, blank=True)
    copertina_img = models.ImageField(upload_to="copertine/", null=True, blank=True)

    def __str__(self):
        return f"{self.titolo} - {self.luogo}"

class EventLike(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_likes")
    event = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "event"], name="unique_user_event_like")
        ]
        indexes = [
            models.Index(fields=["event"]),
            models.Index(fields=["user", "event"]),
        ]

    def __str__(self):
        return f"{self.user.email} ❤️ {self.event_id}"


class FriendRequest(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("canceled", "Canceled"),
    )

    from_user = models.ForeignKey(Utente, related_name="friend_requests_sent", on_delete=models.CASCADE)
    to_user   = models.ForeignKey(Utente, related_name="friend_requests_received", on_delete=models.CASCADE)
    status    = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at   = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="uq_friend_request_one_direction"),
        ]

    def clean(self):
        if self.from_user_id == self.to_user_id:
            raise ValidationError("Non puoi richiedere l'amicizia a te stesso.")

        # vincoli: si può chiedere a persona (to_user.tipo == 'persona')
        if getattr(self.to_user, "tipo", None) != "persona":
            raise ValidationError("Al momento puoi inviare richieste solo a profili 'persona'.")

        # il mittente può essere persona o locale
        if getattr(self.from_user, "tipo", None) not in ("persona", "locale"):
            raise ValidationError("Mittente non valido.")

        # Esiste già amicizia accettata fra i due?
        already_friends = FriendRequest.objects.filter(
            models.Q(from_user=self.from_user, to_user=self.to_user) |
            models.Q(from_user=self.to_user, to_user=self.from_user),
            status="accepted",
        ).exists()
        if already_friends:
            raise ValidationError("Siete già amici.")

        # Evita doppione inverso 'pending'
        inverse_pending = FriendRequest.objects.filter(
            from_user=self.to_user, to_user=self.from_user, status="pending"
        ).exists()
        if inverse_pending:
            raise ValidationError("Esiste già una richiesta pendente in senso opposto.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)