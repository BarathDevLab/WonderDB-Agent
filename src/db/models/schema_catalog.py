from pydantic import BaseModel


class SchemaCatalog(BaseModel):
    tenant_id: str
    table_name: str
    ddl: str
