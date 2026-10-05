from .serializers import AdminSerializer, RoadSerializer, AddressSerializer, LandmarkGeoSerializer

# Landmark Cross Model Search
from rest_framework.views import APIView
from rest_framework.response import Response

# utils
from .utils import *

# api docs
from .api_docs import search_schema


# Create your views here.
class CrossModelSearchView(APIView):
    @search_schema
    def get(self, request):
        params = self.request.query_params
        landmark = params.get('landmark')
        hn = params.get('hn')
        street = params.get('street')
        subdivision = params.get('subd')
        barangay = params.get('brgy')
        municipality = params.get('city')
        
        results = {}
        
        if (street) and not any([landmark, hn ]):
            streets = search_road(street, barangay=barangay, city=municipality)
            results["street"] = RoadSerializer(streets, many=True).data
                
        
        if (barangay or municipality) and not any([landmark, hn, street, subdivision]):
            admin = search_admin(barangay=barangay, city=municipality)
            results["admin"] = AdminSerializer(admin, many=True).data
        
        if landmark:
            landmarks = search_landmark(
                landmark, barangay=barangay, city=municipality, street=street
            )
            results["landmark"] = LandmarkGeoSerializer(landmarks, many=True).data
                
    
        if hn and not any([landmark]):
            addresses  = search_address(
                hn, street=street, subdivision=subdivision, municipality=municipality, barangay=barangay
            )
            
            results["hn"] = AddressSerializer(addresses , many=True).data      
                              
        return Response({"results": results})
    
        