from libs.MCP3008_0 import MCP3008_0 as MCP3008_0_lib
from libs.MCP3008_1 import MCP3008_1 as MCP3008_1_lib
from config.settings import MCP_THRESHOLD

class MCP3008Controller:
    def __init__(self):
        self.mcp1 = MCP3008_0_lib()
        self.mcp2 = MCP3008_1_lib()
        self.threshold = MCP_THRESHOLD
        
    def read_channel(self, mcp_id: int, channel: int) -> int:
        if mcp_id == 0:
            return self.mcp1.read(channel)
        else:
            return self.mcp2.read(channel)
            
    def read_all_channels(self, mcp_id: int) -> List[int]:
        if mcp_id == 0:
            return [self.mcp1.read(i) for i in range(8)]
        else:
            return [self.mcp2.read(i) for i in range(8)]
            
    def is_button_pressed(self, mcp_id: int, channel: int) -> bool:
        return self.read_channel(mcp_id, channel) > self.threshold
        
    def close(self):
        self.mcp1.close()
        self.mcp2.close()
