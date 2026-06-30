from models.parcel import Parcel


def create_parcel(name: str, boundary, area_m2: float) -> Parcel:
    return Parcel(name=name, boundary=boundary, area_m2=area_m2)
