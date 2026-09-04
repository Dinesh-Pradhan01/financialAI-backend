from app.repositories.base import BaseRepository
from app.db.models.vendor import VendorMaster
from app.schemas.vendor import VendorCreate, VendorUpdate

class RepositoryVendor(BaseRepository[VendorMaster, VendorCreate, VendorUpdate]):
    pass

vendor_repository = RepositoryVendor(VendorMaster)
