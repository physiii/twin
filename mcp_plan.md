# LNXlink Custom Shell Command Integration via MCP

## Project Overview

This document describes the implementation of a custom tool in the Machine Conversation Protocol (MCP) that allows running shell commands on a Linux machine via LNXlink and integrates with Home Assistant.

## Objective

Create a complete integration flow where:
1. AI assistants can execute shell commands on a Linux machine via MCP protocol
2. The commands are securely routed through Home Assistant to a specific LNXlink client
3. Command results are returned back to the AI assistant via the MCP protocol

## Components Implemented

### 1. LNXlink Custom Module (`hass_run_command.py`)
We created a custom module for LNXlink that:
- Accepts shell commands via MQTT
- Executes the commands in a controlled environment with timeout support
- Captures stdout, stderr, and return code
- Returns results via MQTT
- Handles proper JSON serialization for input/output

The module is installed at:
```
/home/andy/.local/share/pipx/venvs/lnxlink/lib/python3.12/site-packages/lnxlink/modules/hass_run_command.py
```

### 2. LNXlink Configuration
- Added the module to the LNXlink configuration
- Set up proper MQTT connectivity 
- Configured proper error handling and logging
- Set up as a systemd user service

## Current Status

- ✅ LNXlink module successfully loads and functions
- ✅ Direct MQTT command/response flow works correctly
- ✅ Commands can be executed with appropriate timeout handling
- ✅ Results include stdout, stderr, and return code
- ❌ MCP integration not yet complete (Home Assistant side configuration needed)

The MQTT round-trip works, as demonstrated by the successful command execution:
```
mosquitto_pub -h 192.168.1.40 -p 1883 -t "lnxlink/desktop-linux/commands/hass_run_command/run_command" -m '{"value": "ls /tmp", "timeout": 10}'
```

Result received:
```
lnxlink/desktop-linux/command_result/hass_run_command/run_command {"stdout": "dbus-d0Ujb637eM\ndbus-HMmH6lITxu\nfaiss\n...", "stderr": "", "returncode": 0}
```

## Remaining Steps

### 1. Configure Home Assistant MCP Integration
Add configuration to Home Assistant (running in Docker on 192.168.1.40) to expose our custom command as an MCP tool:

1. Edit Home Assistant's `configuration.yaml` file to add:
   ```yaml
   intent_script:
     HassRunCommand:
       description: "Runs a shell command on a specified LNXlink client"
       slots:
         value:
           description: "The shell command to execute"
           required: true
         timeout:
           description: "Timeout in seconds"
           required: false
       action:
         - service: mqtt.publish
           data:
             topic: "lnxlink/desktop-linux/commands/hass_run_command/run_command"
             payload_template: >
               {{ {"value": value, "timeout": timeout | default(10)} | to_json }}
             qos: 1
             retain: false
         - wait_for_trigger:
             - platform: mqtt
               topic: "lnxlink/desktop-linux/command_result/hass_run_command/run_command"
           timeout: "{{ timeout | default(10) + 5 }}"
           continue_on_timeout: false
         - variables:
             command_output: "{{ trigger.payload_json.stdout | default('') if trigger else 'Error: No response' }}"
             command_error: "{{ trigger.payload_json.stderr | default('') if trigger else '' }}"
             command_returncode: "{{ trigger.payload_json.returncode | default(-1) if trigger else -1 }}"
       speech:
         text: >
           {% if command_returncode == 0 %}
           Command successful. Output: {{ command_output }}
           {% else %}
           Command failed (Code: {{ command_returncode }}). Error: {{ command_error }} Output: {{ command_output }}
           {% endif %}

   # Make sure the intent is exposed to conversation/MCP
   conversation:
     intents:
       - HassRunCommand
   ```

2. Restart Home Assistant Docker container after saving changes:
   ```
   docker restart [home-assistant-container-name]
   ```

3. Check Home Assistant logs for any configuration errors.

### 2. Testing the Complete Integration

Once Home Assistant configuration is complete:

1. Run the MCP test script to verify the full round-trip:
   ```
   cd tools && python mcp_test.py
   ```

2. Expected results:
   - The "Available tools" list should include `HassRunCommand`
   - The call to `HassRunCommand` should execute successfully
   - The output should contain the results of `ls /tmp`

## Security Considerations

- The current implementation allows any shell command to be executed as the LNXlink user
- In production, consider adding command filtering or restriction mechanisms
- Consider restricting which clients/users can invoke this command

## Troubleshooting

If integration issues persist:
1. Check LNXlink logs: `journalctl --user -u lnxlink.service -n 100`
2. Check Home Assistant logs via Docker or UI
3. Verify MQTT connectivity with test messages
4. Confirm Home Assistant MCP configuration exposes the tool correctly

## Future Enhancements

1. Support for specifying which LNXlink client to target (for multi-client setups)
2. Command whitelisting or access control
3. Custom timeout per command type
4. Enhanced error handling and reporting 