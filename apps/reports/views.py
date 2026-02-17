"""
Reports App Views
=================

Dashboard and reporting endpoints for LM-MonoLithic.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .dashboard import DashboardService, get_dashboard_data


class DashboardViewSet(viewsets.ViewSet):
    """
    Dashboard API ViewSet.
    
    Provides aggregated data for the main dashboard including:
    - KPIs (Occupancy, Vacant Area, Rent Collected, Pending Revenue, etc.)
    - Charts (Leased vs Vacant, Rent Due vs Collected, Lease Expiry Ladder)
    - Tables (Upcoming Expiries, Top Overdue Tenants, Vacant Units Aging)
    - Portfolio Map data
    - Occupancy Timeline data
    
    All endpoints are scope-aware and respect multi-tenancy.
    
    Query Parameters:
    - org_ids: Comma-separated organization IDs
    - site_ids: Comma-separated site IDs
    - tower_ids: Comma-separated tower IDs
    - floor_ids: Comma-separated floor IDs
    - unit_ids: Comma-separated unit IDs
    - as_of: As-of date (YYYY-MM-DD)
    - date_from: Start date (YYYY-MM-DD)
    - date_to: End date (YYYY-MM-DD)
    - group_by: Grouping dimension (site, tower, floor)
    """
    
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """
        Get complete dashboard data.
        
        Returns:
            Complete dashboard data including KPIs, charts, tables, and filters
        """
        params = request.query_params
        data = get_dashboard_data(request, params)
        return Response(data)
    
    @action(detail=False, methods=['get'])
    def kpis(self, request):
        """
        Get KPIs only.
        
        Returns:
            KPI data for dashboard cards
        """
        params = request.query_params
        service = DashboardService(request, params)
        return Response(service.get_kpis())
    
    @action(detail=False, methods=['get'])
    def charts(self, request):
        """
        Get charts only.
        
        Returns:
            Chart data for dashboard visualizations
        """
        params = request.query_params
        service = DashboardService(request, params)
        return Response(service.get_charts())
    
    @action(detail=False, methods=['get'])
    def tables(self, request):
        """
        Get tables only.
        
        Returns:
            Table data for dashboard
        """
        params = request.query_params
        service = DashboardService(request, params)
        return Response(service.get_tables())
    
    @action(detail=False, methods=['get'])
    def portfolio_map(self, request):
        """
        Get portfolio map data.
        
        Returns:
            Property pins for portfolio map
        """
        params = request.query_params
        service = DashboardService(request, params)
        return Response(service.get_portfolio_map())
    
    @action(detail=False, methods=['get'])
    def occupancy_timeline(self, request):
        """
        Get occupancy timeline.
        
        Returns:
            Monthly occupancy trend data
        """
        params = request.query_params
        service = DashboardService(request, params)
        return Response(service.get_occupancy_timeline())
    
    @action(detail=False, methods=['get'])
    def filters(self, request):
        """
        Get filter options.
        
        Returns:
            Available filter options
        """
        service = DashboardService(request)
        return Response(service.get_filter_options())
