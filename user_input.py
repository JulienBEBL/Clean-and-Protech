from drivers.mcp3008 import MCP3008Controller
from config.settings import MCP_THRESHOLD

class UserInputController:
    def __init__(self, mcp_controller: MCP3008Controller):
        self.mcp = mcp_controller
        self.threshold = MCP_THRESHOLD
        self.button_states = [0] * 8
        self.selector_states = [0] * 5
        self.air_button_state = 0
        self.program_number = 0
        self.selector_position = 0
        
    def update(self):
        # Read button states from MCP2
        self.button_states = [
            1 if self.mcp.read_channel(1, i) > self.threshold else 0 
            for i in range(8)
        ]
        
        # Determine program number
        if sum(self.button_states) == 1:
            self.program_number = self.button_states.index(1) + 1
        else:
            self.program_number = 0
            
        # Read selector states from MCP1
        self.selector_states = [
            1 if self.mcp.read_channel(0, i) > self.threshold else 0 
            for i in range(5)
        ]
        
        # Determine selector position
        if sum(self.selector_states) == 1:
            self.selector_position = self.selector_states.index(1)
        else:
            self.selector_position = 0
            
        # Read air button state
        self.air_button_state = 1 if self.mcp.read_channel(0, 5) > self.threshold else 0
        
    def wait_for_button_release(self):
        # Implementation of waiting for button release
        # ... (code from original attendre_relachement_boutons function)
        pass
        
    def confirm_program(self, program_number: int, timeout: float = 10.0) -> bool:
        # Implementation of program confirmation
        # ... (code from original confirmer_programme function)
        pass
