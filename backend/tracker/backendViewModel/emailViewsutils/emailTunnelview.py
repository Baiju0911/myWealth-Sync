import os
import urllib.request
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class CloudflareTunnelViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    PUBLIC_TUNNEL_URL = os.getenv(
        "CLOUDFLARE_TUNNEL_PUBLIC_URL", "https://ingest.bluedotservices.net"
    )
    INTERNAL_METRICS_URL = os.getenv(
        "CLOUDFLARE_TUNNEL_METRICS_URL", "http://quick_tunnel:20000/ready"
    )

    def _get_dynamic_tunnel_url(self):
        return self.PUBLIC_TUNNEL_URL.rstrip("/")

    @action(detail=False, methods=["get"], url_path="status")
    def get_status(self, request):
        active_tunnel_url = self._get_dynamic_tunnel_url()
        edge_location = os.getenv("CLOUDFLARE_EDGE_LOCATION", "maa05 (Chennai)")
        protocol = os.getenv("CLOUDFLARE_TUNNEL_PROTOCOL", "QUIC")
        is_healthy = False

        try:
            req = urllib.request.urlopen(self.INTERNAL_METRICS_URL, timeout=1.5)
            if req.status == 200:
                is_healthy = True
        except Exception:
            try:
                public_check_url = (
                    f"{active_tunnel_url}/api/ingest/email/tunnel/inspect-endpoint/"
                )
                req = urllib.request.urlopen(public_check_url, timeout=2.0)
                if req.status in [200, 404, 405]:
                    is_healthy = True
            except Exception as e:
                print(f"⚠️ Tunnel Health Check Error: {e}")

        if is_healthy:
            return Response(
                {
                    "status": "ONLINE",
                    "tunnel_url": active_tunnel_url,
                    "ingest_endpoint": f"{active_tunnel_url}/api/ingest/email/staging/ingest/?confirm=false",
                    "protocol": protocol,
                    "edge_location": edge_location,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": "OFFLINE",
                "tunnel_url": None,
                "ingest_endpoint": None,
                "protocol": None,
                "edge_location": None,
                "error": "Cloudflare Tunnel service unreachable.",
            },
            status=status.HTTP_200_OK,
        )
