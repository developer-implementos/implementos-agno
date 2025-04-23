from pathlib import Path
from typing import List, Optional, Union, Dict, Any

from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger


class ShellTools(Toolkit):
    def __init__(self, base_dir: Optional[Union[Path, str]] = None):
        super().__init__(name="shell_tools")

        self.base_dir: Optional[Path] = None
        if base_dir is not None:
            self.base_dir = Path(base_dir) if isinstance(base_dir, str) else base_dir

        # Registrar funciones
        self.register(self.run_shell_command)
        self.register(self.ssh_connect)
        self.register(self.ssh_run_command)
        self.register(self.scp_transfer)
        self.register(self.ssh_run_interactive_commands)  # Registrar la nueva función
        
        # Diccionario para mantener conexiones SSH activas
        self._ssh_connections: Dict[str, Any] = {}

    def run_shell_command(self, args: List[str], tail: int = 100) -> str:
        """Runs a shell command and returns the output or error.

        Args:
            args (List[str]): The command to run as a list of strings.
            tail (int): The number of lines to return from the output.
        Returns:
            str: The output of the command.
        """
        import subprocess

        try:
            log_info(f"Running shell command: {args}")
            if self.base_dir:
                args = ["cd", str(self.base_dir), ";"] + args
            result = subprocess.run(args, capture_output=True, text=True)
            log_debug(f"Result: {result}")
            log_debug(f"Return code: {result.returncode}")
            if result.returncode != 0:
                return f"Error: {result.stderr}"
            # return only the last n lines of the output
            return "\n".join(result.stdout.split("\n")[-tail:])
        except Exception as e:
            logger.warning(f"Failed to run shell command: {e}")
            return f"Error: {e}"
    
    def ssh_connect(
        self,
        hostname: str,
        username: str,
        password: Optional[str] = None,
        port: int = 22,
        key_filename: Optional[str] = None,
        passphrase: Optional[str] = None,
        connection_id: Optional[str] = None
    ) -> str:
        """Establece una conexión SSH a un servidor remoto.

        Args:
            hostname (str): Nombre o dirección IP del servidor.
            username (str): Nombre de usuario para la conexión.
            password (Optional[str]): Contraseña para autenticación. Default: None.
            port (int): Puerto SSH. Default: 22.
            key_filename (Optional[str]): Ruta al archivo de clave privada. Default: None.
            passphrase (Optional[str]): Frase de contraseña para la clave privada. Default: None.
            connection_id (Optional[str]): Identificador único para esta conexión. Default: None.

        Returns:
            str: Mensaje que indica el éxito o fracaso de la conexión.
        """
        try:
            import paramiko
            
            log_info(f"Estableciendo conexión SSH a {hostname}:{port} como {username}")
            
            # Generar ID de conexión si no se proporcionó
            if connection_id is None:
                connection_id = f"{username}@{hostname}:{port}"
            
            # Crear cliente SSH
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Establecer la conexión
            connect_kwargs = {
                "hostname": hostname,
                "port": port,
                "username": username
            }
            
            # Añadir autenticación
            if password:
                connect_kwargs["password"] = password
            if key_filename:
                connect_kwargs["key_filename"] = key_filename
            if passphrase:
                connect_kwargs["passphrase"] = passphrase
                
            client.connect(**connect_kwargs)
            
            # Guardar la conexión en el diccionario
            self._ssh_connections[connection_id] = client
            
            return f"Conexión SSH establecida exitosamente (ID: {connection_id})"
            
        except ImportError:
            return "Error: Se requiere el módulo 'paramiko'. Instálalo con: pip install paramiko"
        except Exception as e:
            logger.warning(f"Error al establecer conexión SSH: {e}")
            return f"Error: {str(e)}"
    
    def ssh_run_command(
        self,
        command: str,
        connection_id: str,
        tail: int = 100,
        timeout: int = 30
    ) -> str:
        """Ejecuta un comando en un servidor remoto a través de SSH.

        Args:
            command (str): Comando a ejecutar.
            connection_id (str): ID de la conexión SSH establecida anteriormente.
            tail (int): Número de líneas a devolver del resultado. Default: 100.
            timeout (int): Tiempo de espera en segundos. Default: 30.

        Returns:
            str: Salida del comando o mensaje de error.
        """
        try:
            if connection_id not in self._ssh_connections:
                return f"Error: No existe conexión SSH con ID: {connection_id}"
            
            client = self._ssh_connections[connection_id]
            log_info(f"Ejecutando comando remoto: {command}")
            
            # Ejecutar el comando
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            
            # Obtener salida y errores
            stdout_str = stdout.read().decode('utf-8')
            stderr_str = stderr.read().decode('utf-8')
            
            # Verificar el código de salida
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                return f"Error (código {exit_status}): {stderr_str}"
            
            # Devolver solo las últimas n líneas
            result = "\n".join(stdout_str.split("\n")[-tail:])
            return result
            
        except Exception as e:
            logger.warning(f"Error al ejecutar comando SSH: {e}")
            return f"Error: {str(e)}"
    
    def ssh_run_interactive_commands(
    self,
    commands: List[str],
    expected_prompts: List[str],
    inputs: List[str],
    connection_id: str,
    timeout: int = 30,
    prompt_timeout: int = 5,
    command_timeout: int = 120,
    terminal_prompt: str = "$"
) -> str:
        """Ejecuta una secuencia de comandos interactivos en un servidor remoto.
        
        Permite ejecutar comandos que requieren entrada del usuario, como 'sudo su' 
        seguido de una contraseña y luego ejecutar comandos adicionales en ese contexto.
        
        Args:
            commands (List[str]): Lista de comandos a ejecutar en secuencia.
            expected_prompts (List[str]): Lista de prompts esperados antes de enviar cada input.
            inputs (List[str]): Lista de entradas a enviar después de cada prompt.
            connection_id (str): ID de la conexión SSH establecida anteriormente.
            timeout (int): Tiempo de espera en segundos para cada operación. Default: 30.
            prompt_timeout (int): Tiempo máximo de espera para un prompt específico. Default: 5.
            command_timeout (int): Tiempo máximo de espera para que termine un comando. Default: 120.
            terminal_prompt (str): Patrón que indica que el comando ha terminado (típicamente $ o >). Default: "$".
        
        Returns:
            str: Salida completa de la sesión interactiva o mensaje de error.
        """
        try:
            if connection_id not in self._ssh_connections:
                return f"Error: No existe conexión SSH con ID: {connection_id}"
            
            client = self._ssh_connections[connection_id]
            log_info(f"Iniciando sesión interactiva con comandos: {commands}")
            
            # Abrir un canal para comunicación interactiva
            channel = client.invoke_shell()
            output = ""
            
            # Configurar timeout
            channel.settimeout(timeout)
            
            import time
            
            # Leer el prompt inicial
            time.sleep(1)
            if channel.recv_ready():
                initial_output = channel.recv(4096).decode('utf-8', errors='replace')
                output += initial_output
                log_debug(f"Prompt inicial: {initial_output}")
            
            # Iterar a través de cada comando
            for i, command in enumerate(commands):
                # Enviar el comando
                log_info(f"Enviando comando: {command}")
                channel.send(command + "\n")
                
                # Esperar un momento para que el comando comience
                time.sleep(0.5)
                
                # Si hay un prompt esperado y un input para este comando
                if i < len(expected_prompts) and i < len(inputs) and expected_prompts[i]:
                    prompt_found = False
                    start_time = time.time()
                    buffer = ""
                    
                    # Esperar al prompt con un tiempo límite
                    while not prompt_found and (time.time() - start_time) < prompt_timeout:
                        if channel.recv_ready():
                            chunk = channel.recv(4096).decode('utf-8', errors='replace')
                            buffer += chunk
                            output += chunk
                            log_debug(f"Buffer: {buffer}")
                            
                            # Verificar si el prompt esperado está en el buffer
                            if expected_prompts[i] in buffer:
                                prompt_found = True
                                break
                        
                        time.sleep(0.1)
                    
                    if not prompt_found:
                        log_info(f"Advertencia: Prompt '{expected_prompts[i]}' no encontrado en {prompt_timeout}s")
                        # Si no encontramos el prompt exacto, verificamos si hay algo similar
                        if "password" in expected_prompts[i].lower() and "contraseña" in buffer.lower():
                            log_info("Se detectó un prompt de contraseña alternativo")
                            prompt_found = True
                    
                    # Enviar el input correspondiente
                    if prompt_found or expected_prompts[i]:
                        log_info(f"Enviando input para prompt")
                        channel.send(inputs[i] + "\n")
                
                # Esperar a que el comando termine
                command_complete = False
                command_start_time = time.time()
                no_data_counter = 0
                last_data_time = time.time()
                
                while not command_complete and (time.time() - command_start_time) < command_timeout:
                    if channel.recv_ready():
                        chunk = channel.recv(4096).decode('utf-8', errors='replace')
                        output += chunk
                        log_debug(f"Recibidos {len(chunk)} bytes")
                        last_data_time = time.time()
                        no_data_counter = 0
                        
                        # Verificar si el comando ha terminado (aparece el prompt del terminal)
                        if terminal_prompt in chunk or "@" in chunk:
                            log_info(f"Se detectó el prompt del terminal - comando completado")
                            command_complete = True
                            break
                    else:
                        time.sleep(0.2)
                        no_data_counter += 1
                        
                        # Si no hay datos nuevos durante un tiempo, verificamos si ha terminado
                        if no_data_counter > 15:  # ~3 segundos sin datos nuevos
                            # Enviar un carácter nulo para ver si hay respuesta
                            channel.send("")
                            time.sleep(0.1)
                            if channel.recv_ready():
                                # Si hay respuesta, reiniciamos el contador
                                no_data_counter = 0
                            else:
                                # Si no hay respuesta y ha pasado suficiente tiempo sin datos
                                # podemos asumir que el comando ha terminado
                                if time.time() - last_data_time > 5:
                                    log_info(f"No hay nuevos datos en 5 segundos - asumiendo que el comando ha terminado")
                                    command_complete = True
                                    break
                
                if not command_complete:
                    log_info(f"Advertencia: El comando no terminó dentro del tiempo límite de {command_timeout} segundos")
                    # Intentar interrumpir el comando si se quedó atascado
                    channel.send("\x03")  # Enviar Ctrl+C
            
            # Cerrar el canal
            channel.close()
            
            return output
            
        except Exception as e:
            logger.warning(f"Error en sesión interactiva SSH: {e}")
            return f"Error: {str(e)}"
    def scp_transfer(
        self,
        connection_id: str,
        local_path: str,
        remote_path: str,
        upload: bool = True
    ) -> str:
        """Transfiere archivos entre el sistema local y el remoto usando SCP.

        Args:
            connection_id (str): ID de la conexión SSH establecida anteriormente.
            local_path (str): Ruta al archivo local.
            remote_path (str): Ruta al archivo remoto.
            upload (bool): True para subir, False para descargar. Default: True.

        Returns:
            str: Mensaje que indica el éxito o fracaso de la transferencia.
        """
        try:
            if connection_id not in self._ssh_connections:
                return f"Error: No existe conexión SSH con ID: {connection_id}"
            
            client = self._ssh_connections[connection_id]
            sftp = client.open_sftp()
            
            try:
                if upload:
                    log_info(f"Subiendo archivo: {local_path} → {remote_path}")
                    sftp.put(local_path, remote_path)
                    return f"Archivo subido exitosamente: {local_path} → {remote_path}"
                else:
                    log_info(f"Descargando archivo: {remote_path} → {local_path}")
                    sftp.get(remote_path, local_path)
                    return f"Archivo descargado exitosamente: {remote_path} → {local_path}"
            finally:
                sftp.close()
                
        except Exception as e:
            logger.warning(f"Error en transferencia SCP: {e}")
            return f"Error: {str(e)}"
    
    def close_ssh_connection(self, connection_id: str) -> str:
        """Cierra una conexión SSH específica.

        Args:
            connection_id (str): ID de la conexión a cerrar.

        Returns:
            str: Mensaje indicando el resultado.
        """
        if connection_id not in self._ssh_connections:
            return f"Error: No existe conexión SSH con ID: {connection_id}"
        
        try:
            self._ssh_connections[connection_id].close()
            del self._ssh_connections[connection_id]
            return f"Conexión SSH cerrada exitosamente (ID: {connection_id})"
        except Exception as e:
            logger.warning(f"Error al cerrar conexión SSH: {e}")
            return f"Error al cerrar conexión: {str(e)}"
    
    def close_all_ssh_connections(self) -> str:
        """Cierra todas las conexiones SSH activas.

        Returns:
            str: Mensaje indicando el número de conexiones cerradas.
        """
        count = len(self._ssh_connections)
        if count == 0:
            return "No hay conexiones SSH activas para cerrar."
        
        errors = []
        for connection_id, client in list(self._ssh_connections.items()):
            try:
                client.close()
                del self._ssh_connections[connection_id]
            except Exception as e:
                errors.append(f"{connection_id}: {str(e)}")
        
        if errors:
            return f"Se cerraron {count - len(errors)} de {count} conexiones. Errores: {', '.join(errors)}"
        else:
            return f"Se cerraron {count} conexiones SSH exitosamente."
    
    def __del__(self):
        """Destructor que asegura cerrar todas las conexiones SSH al finalizar."""
        for client in self._ssh_connections.values():
            try:
                client.close()
            except:
                pass