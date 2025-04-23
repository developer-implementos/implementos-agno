from pathlib import Path
from typing import List, Optional, Union, Dict, Any

from agno.tools import Toolkit
from agno.utils.log import log_debug, log_info, logger


class RemoteDeployTools(Toolkit):
    """Herramientas para gestionar archivos locales y desplegarlos en servidores remotos."""
    
    def __init__(self, base_dir: Optional[Union[Path, str]] = None):
        super().__init__(name="remote_deploy_tools")

        # Configurar directorio base
        self.base_dir: Path = Path(base_dir) if isinstance(base_dir, str) else (base_dir or Path.cwd())
        
        # Diccionario para mantener conexiones SSH activas
        self._ssh_connections: Dict[str, Any] = {}
        
        # Registrar funciones
        # Funciones de archivos locales
        self.register(self.save_file, sanitize_arguments=False)
        self.register(self.read_file)
        self.register(self.list_files)
        self.register(self.delete_file)
        
        # Funciones SSH
        self.register(self.ssh_connect)
        self.register(self.ssh_run_command)
        self.register(self.ssh_run_interactive_commands)
        self.register(self.ssh_run_as_root)
        self.register(self.scp_transfer)
        self.register(self.close_ssh_connection)
        self.register(self.close_all_ssh_connections)
        
        # Funciones combinadas
        self.register(self.create_and_upload_file)
      
    # ==================== Funciones de archivos locales ====================
    
    def save_file(self, contents: str, file_name: str, overwrite: bool = True) -> str:
        """Guarda el contenido en un archivo local.

        Args:
            contents (str): El contenido a guardar.
            file_name (str): Nombre del archivo.
            overwrite (bool): Sobrescribir si existe. Default: True.
        
        Returns:
            str: Nombre del archivo o mensaje de error.
        """
        try:
            file_path = self.base_dir.joinpath(file_name)
            log_debug(f"Guardando contenido en {file_path}")
            if not file_path.parent.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)
            if file_path.exists() and not overwrite:
                return f"El archivo {file_name} ya existe"
            file_path.write_text(contents)
            log_info(f"Guardado: {file_path}")
            return str(file_name)
        except Exception as e:
            logger.error(f"Error al guardar archivo: {e}")
            return f"Error al guardar archivo: {e}"

    def read_file(self, file_name: str) -> str:
        """Lee el contenido de un archivo local.

        Args:
            file_name (str): Nombre del archivo a leer.
        
        Returns:
            str: Contenido del archivo o mensaje de error.
        """
        try:
            log_info(f"Leyendo archivo: {file_name}")
            file_path = self.base_dir.joinpath(file_name)
            contents = file_path.read_text()
            return str(contents)
        except Exception as e:
            logger.error(f"Error al leer archivo: {e}")
            return f"Error al leer archivo: {e}"

    def list_files(self) -> str:
        """Lista los archivos en el directorio base.

        Returns:
            str: Lista de archivos en formato JSON o mensaje de error.
        """
        try:
            import json
            log_info(f"Leyendo archivos en: {self.base_dir}")
            return json.dumps([str(file_path) for file_path in self.base_dir.iterdir()], indent=4)
        except Exception as e:
            logger.error(f"Error al listar archivos: {e}")
            return f"Error al listar archivos: {e}"
    
    def delete_file(self, file_name: str) -> str:
        """Elimina un archivo o directorio local.

        Args:
            file_name (str): Nombre del archivo o directorio a eliminar.
        
        Returns:
            str: Mensaje de éxito o error.
        """
        try:
            path_to_del = self.base_dir.joinpath(file_name)
            log_info(f"Eliminando: {path_to_del}")
            
            if not path_to_del.exists():
                return f"El archivo {file_name} no existe"
                
            if path_to_del.is_dir():
                from shutil import rmtree
                rmtree(path=path_to_del, ignore_errors=True)
            else:
                path_to_del.unlink()
                
            if not path_to_del.exists():
                return f"Archivo {file_name} eliminado correctamente"
            else:
                return f"No se pudo eliminar {file_name}"
                
        except Exception as e:
            logger.error(f"Error al eliminar archivo: {e}")
            return f"Error al eliminar archivo: {e}"
    
    # ==================== Funciones SSH ====================
    
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
            terminal_prompt (str): Patrón que indica que el comando ha terminado. Default: "$".
        
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
    
    def ssh_run_as_root(
        self,
        commands: List[str],
        connection_id: str,
        sudo_password: str,
        timeout: int = 300
    ) -> str:
        """Ejecuta comandos como usuario root en un servidor remoto.
        
        Se encarga automáticamente de hacer sudo su, ejecutar los comandos y salir.
        
        Args:
            commands (List[str]): Lista de comandos a ejecutar como root.
            connection_id (str): ID de la conexión SSH establecida anteriormente.
            sudo_password (str): Contraseña para sudo.
            timeout (int): Tiempo máximo de espera por comando en segundos. Default: 300.
        
        Returns:
            str: Salida completa de la sesión o mensaje de error.
        """
        try:
            # Preparar la lista completa de comandos
            full_commands = ["sudo su -"]
            full_commands.extend(commands)
            full_commands.append("exit")  # Asegurar que salimos de la sesión root
            
            # Preparar la lista de prompts esperados
            expected_prompts = ["contraseña|password"]  # Expresión para detectar prompt de contraseña
            root_prompt = "root@.*[#$]"  # Expresión para detectar prompt de root
            
            # Por cada comando, esperar el prompt de root (excepto para el primero y el último)
            cmd_prompts = [root_prompt] * (len(commands))
            expected_prompts.extend(cmd_prompts)
            expected_prompts.append("")  # No hay prompt para el comando exit
            
            # Preparar las entradas
            inputs = [sudo_password]  # Contraseña para sudo
            inputs.extend([""] * (len(commands) + 1))  # Sin entrada para los demás comandos
            
            # Ejecutar los comandos
            log_info(f"Ejecutando {len(commands)} comandos como root")
            return self.ssh_run_interactive_commands(
                commands=full_commands,
                expected_prompts=expected_prompts,
                inputs=inputs,
                connection_id=connection_id,
                prompt_timeout=10,
                command_timeout=timeout,
                terminal_prompt="#"  # Prompt de root
            )
        
        except Exception as e:
            logger.warning(f"Error al ejecutar comandos como root: {e}")
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
    
    # ==================== Funciones combinadas ====================
    
    def create_and_upload_file(
        self, 
        contents: str, 
        file_name: str, 
        connection_id: str, 
        remote_path: str,
        make_executable: bool = False
    ) -> str:
        """Crea un archivo local y lo sube a un servidor remoto.
        
        Args:
            contents (str): Contenido del archivo.
            file_name (str): Nombre del archivo local.
            connection_id (str): ID de la conexión SSH.
            remote_path (str): Ruta completa en el servidor remoto.
            make_executable (bool): Si es True, hace el archivo ejecutable en el servidor. Default: False.
            
        Returns:
            str: Mensaje indicando el resultado.
        """
        try:
            # Primero guardamos el archivo localmente
            save_result = self.save_file(contents, file_name)
            if "Error" in save_result:
                return save_result
                
            # Luego lo subimos al servidor
            local_path = str(self.base_dir.joinpath(file_name))
            upload_result = self.scp_transfer(connection_id, local_path, remote_path, upload=True)
            
            if "Error" in upload_result:
                return upload_result
                
            # Si se solicita, hacer el archivo ejecutable
            if make_executable:
                chmod_result = self.ssh_run_command(f"chmod +x {remote_path}", connection_id)
                if "Error" in chmod_result:
                    return f"Archivo subido pero no se pudo hacer ejecutable: {chmod_result}"
                    
                return f"Archivo creado, subido y hecho ejecutable: {remote_path}"
            
            return f"Archivo creado y subido exitosamente: {remote_path}"
            
        except Exception as e:
            logger.warning(f"Error al crear y subir archivo: {e}")
            return f"Error: {str(e)}"
    
    def __del__(self):
        """Destructor que asegura cerrar todas las conexiones SSH al finalizar."""
        for client in self._ssh_connections.values():
            try:
                client.close()
            except:
                pass