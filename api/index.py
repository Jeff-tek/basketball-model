import sys
sys.path.insert(0, ".")

from server.main import app
from mangum import Mangum

app.root_path = "/api"
handler = Mangum(app)
