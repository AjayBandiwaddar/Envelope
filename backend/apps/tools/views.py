"""Views for the Tools API (API_SPEC.md Section 13). Administrative endpoints only."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.authentication import AdminTokenAuthentication

from .models import Tool, ToolStatus
from .serializers import ToolCreateSerializer, ToolSerializer


class ToolListCreateView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tools = Tool.objects.all()
        data = ToolSerializer(tools, many=True).data
        return Response({"data": data, "request_id": getattr(request, "request_id", "")})

    def post(self, request):
        serializer = ToolCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tool = serializer.save()
        data = ToolSerializer(tool).data
        return Response({"data": data, "request_id": getattr(request, "request_id", "")}, status=201)


class ToolDetailView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, tool_id):
        tool = Tool.objects.filter(tool_id=tool_id).first()
        if tool is None:
            return Response(
                {"error": {"code": "TOOL_NOT_FOUND", "message": "Tool not found.", "details": {}},
                 "request_id": getattr(request, "request_id", "")},
                status=404,
            )
        return Response({"data": ToolSerializer(tool).data, "request_id": getattr(request, "request_id", "")})


class ToolDisableView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, tool_id):
        tool = Tool.objects.filter(tool_id=tool_id).first()
        if tool is None:
            return Response(
                {"error": {"code": "TOOL_NOT_FOUND", "message": "Tool not found.", "details": {}},
                 "request_id": getattr(request, "request_id", "")},
                status=404,
            )
        tool.status = ToolStatus.DISABLED
        tool.save(update_fields=["status", "updated_at"])
        return Response(
            {"data": {"tool_id": tool.tool_id, "status": tool.status},
             "request_id": getattr(request, "request_id", "")}
        )