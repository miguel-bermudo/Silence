import importlib
import json

from os import listdir, getcwd, path, mkdir, makedirs
from os.path import splitext

from silence.sql.tables import get_tables, get_views, get_primary_key

from silence.logging.default_logger import logger

from shutil import rmtree


# SILENCE CREATEAPI OPERATIONS

# Entry point for cli command
def create_api():
    existing_routes_method_pairs = get_user_endpoints()
    logger.info("found the following user defined endpoints:\n")
    for rmp in existing_routes_method_pairs:
        logger.info(rmp)

    create_entity_endpoints(existing_routes_method_pairs)

###############################################################################
# Create generic .js files for consuming the created endpoints.
###############################################################################  
# TODO: this is not a very elegant solution as we bruteforce the text parsing. 
# Multiple elements repeat so it can probably be made into various functions.
def generate_API_file_for_endpoints(endpoints, name):
    curr_dir = getcwd()
    api_path = curr_dir + "/docs/js/api"
    
    if not path.isdir(api_path):
        makedirs(api_path)

    logger.info(f"Generating api files for {name}")

    file_content = "//DO NOT EDIT THIS FILE it is auto-generated, it will be updated automatically,\n//all changes done to this file will be lost upon re-running the 'silence createapi' command \n//if you want to create new api entry points define them in a new file.\n" 
    file_content += "'use_strict';\n\nimport { BASE_URL, requestOptions } from './common.js';\n\nconst " + f"{name}APIAuto = " + "{"
    
    for endpoint in endpoints:
        operation = endpoint[0]
        route = endpoint[1]
        method = endpoint[2]
        id_plain = endpoint[3]
        description = endpoint[4]
        id_var = "${" + f"{id_plain}" + "}"

        file_content += "\n\n"
        if method == "GET":
            if "$" in route:
                route = f"{name}/{id_var}"
                file_content += generate_api_text(operation, description, method.lower(), route, id_plain, unique_result=True)
            else:
                route = f"{name}"
                file_content += generate_api_text(operation, description, method.lower(), route)

        elif method == "POST":
            route = f"{name}"
            file_content += generate_api_text(operation, description, method.lower(), route, has_body_params=True)

        elif method == "DELETE":
            route = f"{name}/{id_var}"
            file_content += generate_api_text(operation, description, method.lower(), route, id_plain)

        elif method == "PUT":
            route = f"{name}/{id_var}"
            file_content += generate_api_text(operation, description, method.lower(), route, id_plain, True)

    file_content += "\n};\n\nexport {" + f"{name}APIAuto" +"};"

    api_path + f"{name}.js"

    with open(f"{api_path}/{name}_auto.js", "w") as api_point:
        api_point.write(file_content)

def generate_api_text(operation, description, method, route, id_plain = "", has_body_params = False, unique_result = False):
    file_content = ""
    file_content += f"/**\n* {description}\n*/\n{operation}: function("
    
    if has_body_params:
        file_content += "formData"
        if id_plain != "":
            file_content += ","
    
    file_content += f"{id_plain})"
    file_content += "{\nreturn new Promise (function (resolve, reject) {\n     axios\n          "
    file_content += f".{method}(" + "`${BASE_URL}/" + f"{route}`,"

    if has_body_params:
        file_content +="formData,"

    file_content+= "requestOptions)\n          .then(response => resolve(response.data"
    if unique_result:
        file_content += "[0]"
    file_content+= "))\n          .catch(error => reject(error.response.data.message));\n     });\n},"

    return file_content

###############################################################################
# Get the entities from the database and the existing user endpoints and 
# create CRUD endpoint files (json) for the remaining ones.
###############################################################################
def create_entity_endpoints(existing_routes_method_pairs):
    # Folder handling

    curr_dir = getcwd()
    endpoints_dir_new = curr_dir + "/endpoints"
    endpoints_dir_old = curr_dir + "/api"

    if path.isdir(endpoints_dir_old):
        warnign_old_folder()
        endpoints_dir = endpoints_dir_old

        if path.isdir(endpoints_dir_new):
            endpoints_dir = endpoints_dir_new
            logger.warning("You appear to have both api/ and endpoints/ folders, the latter will be used.")
    
    elif path.isdir(endpoints_dir_new):
        endpoints_dir = endpoints_dir_new
    
    auto_dir = endpoints_dir + "/default"

    logger.debug(f"selected endpoint directory -->  {auto_dir}")
    try:
        rmtree(auto_dir)
    except FileNotFoundError:
        logger.debug("Folder is not there, creating it.")
    
    logger.debug(f"re-creating directory -->  {auto_dir}")
    mkdir(auto_dir)

    # Endpoint files creation
    tables = get_tables()
    
    for table in list(tables.items()):
        pk = get_primary_key(table[0])[0]['Column_name']
        endpoints = {}
        table[1].remove(pk)

        name = table[0]
        ep_tuples = []

        logger.info(f"Generating endpoints for {name}")

        get_all_route = f"/{name}"
        if((get_all_route,"GET") not in existing_routes_method_pairs):
            endpoints["getAll"] = generate_get_all(get_all_route, table)
            endpoint = ("getAll", get_all_route, "GET", pk, endpoints["getAll"]["description"])
            ep_tuples.append(endpoint)


        get_by_id_route = f"/{name}/${pk}"
        if((get_by_id_route,"GET") not in existing_routes_method_pairs):
            endpoints["getById"] = generate_get_by_id(get_by_id_route,table, pk)
            endpoint = ("getById", get_by_id_route, "GET", pk, endpoints["getById"]["description"])
            ep_tuples.append(endpoint)

        create_route = f"/{name}"
        if((create_route, "POST") not in existing_routes_method_pairs):
            endpoints["create"] = generate_create(create_route,table, pk)
            endpoint = ("create", create_route, "POST", pk, endpoints["create"]["description"])
            ep_tuples.append(endpoint)

        udpate_route = f"/{name}/${pk}"
        if((udpate_route,"PUT") not in existing_routes_method_pairs):
            endpoints["update"] = generate_update(udpate_route,table, pk)
            endpoint = ("update", udpate_route, "PUT", pk, endpoints["update"]["description"])
            ep_tuples.append(endpoint)

        delete_route = f"/{name}/${pk}"
        if((delete_route,"DELETE") not in existing_routes_method_pairs):
            endpoints["delete"] = generate_delete(delete_route,table, pk)
            endpoint = ("delete", delete_route, "DELETE", pk, endpoints["delete"]["description"])
            ep_tuples.append(endpoint)

        generate_API_file_for_endpoints(ep_tuples, name)
        dicts_to_file(endpoints, name, auto_dir)
    

    views = get_views()
    for view in list(views.items()):
        endpoints = {}
        ep_tuples = []
        name = view[0]
        logger.info(f"Generating endpoints for {name}")

        get_all_route = f"/{name}"
        if((get_all_route, "GET") not in existing_routes_method_pairs):
            endpoints["getAll"] = generate_get_all(get_all_route, view)
            endpoint = ("getAll", get_all_route, "GET", pk, endpoints["getAll"]["description"])
            ep_tuples.append(endpoint)

        generate_API_file_for_endpoints(ep_tuples, name)
        dicts_to_file(endpoints, view[0], auto_dir)


def get_user_endpoints():
    logger.debug("Looking for user endpoints")

    # Load every .json file inside the endpoints/ or api/ folders
    curr_dir = getcwd()
    endpoints_dir_new = curr_dir + "/endpoints"
    endpoints_dir_old = curr_dir + "/api"

    if not path.isdir(endpoints_dir_old) or not path.isdir(endpoints_dir_new):
        mkdir(endpoints_dir_new)


    if path.isdir(endpoints_dir_old):
        warnign_old_folder()
        endpoints_dir = endpoints_dir_old

        if path.isdir(endpoints_dir_new):
            endpoints_dir = endpoints_dir_new
            logger.warning("You appear to have both api/ and endpoints/ folders, the latter will be used.")
    
    elif path.isdir(endpoints_dir_new):
        endpoints_dir = endpoints_dir_new

    endpoint_paths_json_user = [endpoints_dir + f"/{f}" for f in listdir(endpoints_dir) if f.endswith('.json')]
    endpoint_route_method_pairs = []

    for jsonfile in endpoint_paths_json_user:
        with open(jsonfile, "r") as ep:
            endpoints = list(json.load(ep).values())
            path_parts = jsonfile.split("/")

            endpoint_pairs = [(endpoint['route'], endpoint['method']) for endpoint in endpoints]
            endpoint_route_method_pairs += endpoint_pairs
           

    # SUPPORT FOR .PY FILES:
    pyfiles = [endpoints_dir + f"/{f}" for f in listdir(endpoints_dir) if f.endswith('.py')]
    endpoint_pairs = []
    for pyfile in pyfiles:
        with open(pyfile,"r") as f:
            reader = f.read()

            for ep in reader.split("@endpoint("):
                params = ep.split(")")[0]
                pair = ["",""]
                has_route, has_method = False, False

                for p in params.split((",")):
                    if "route" in p:
                        pair[0] = p.split("=")[1].replace("\"", "").strip()
                        has_route = True
                        
                    elif "method" in p:
                        pair[1] = p.split("=")[1].replace("\"", "").strip()
                        has_method = True

                if has_route and has_method: endpoint_pairs.append(tuple(pair))

    endpoint_route_method_pairs += endpoint_pairs

    return endpoint_route_method_pairs


def dicts_to_file(dicts, name, auto_dir):
    if(dicts):
        all_jsons = "{\n"
        for d in list(dicts.items()):
            all_jsons += "\""+str(d[0]) +"\":" +json.dumps(d[1], indent=2) + ",\n"
        
        all_jsons = all_jsons[:-2]
        all_jsons += " \n}"
        with open(auto_dir+f"/{name}.json", "w") as endpoint:
            endpoint.write(all_jsons)


def generate_get_all(route,table):
    res = {}
    name = table[0]
    res["route"] = route
    res["method"] = "GET"
    res["sql"] = f"SELECT * FROM {name}"
    # res["auth_required"] = False
    # res["allowed_roles"] = ["*"]
    res["description"] = f"Gets all {name}"
    # res["request_body_params"] = []

    return res

def generate_get_by_id(route,table, pk):
    res = {}
    name = table[0]
    res["route"] = route
    res["method"] = "GET"
    res["sql"] = f"SELECT * FROM {name} WHERE {pk} = ${pk}"
    # res["auth_required"] = False
    # res["allowed_roles"] = ["*"]
    res["description"] = f"Gets a {name} with corresponding primary key"
    # res["request_body_params"] = []
    return res

def generate_create(route,table, pk):
    res = {}
    name = table[0]
    param_list = table[1]

    res["route"] = route
    res["method"] = "POST"
    res["sql"] = f"INSERT INTO {name}" + params_to_string(param_list, "", is_create=True) + " VALUES " + params_to_string(param_list, "$", is_create=True)
    res["auth_required"] = True
    # res["allowed_roles"] = ["*"]
    res["description"] = f"creates a new {name}"
    res["request_body_params"] = param_list
    return res

def generate_update(route,table, pk):
    res = {}
    name = table[0]
    param_list = table[1]

    res["route"] = route
    res["method"] = "PUT"
    res["sql"] = f"UPDATE {name} SET " + params_to_string(param_list, "", is_update=True) + f" WHERE {pk} = ${pk}"
    res["auth_required"] = True
    # res["allowed_roles"] = ["*"]
    res["description"] = f"updates an existing {name} with corresponding primary key"
    res["request_body_params"] = param_list
    return res

def generate_delete(route,table,pk):
    res = {}
    name = table[0]
    res["route"] = route
    res["method"] = "DELETE"
    res["sql"] = f"DELETE FROM {name} WHERE {pk} = ${pk}"
    res["auth_required"] = True
    # res["allowed_roles"] = ["*"]
    res["description"] = f"deletes an existing {name} with corresponding primary key"
    # res["request_body_params"] = []
    return res

def params_to_string(param_list, char_add, is_create = False, is_update = False):
    if is_create:
        res = "("
        for p in param_list:
            res += char_add + p +", "
        res = res[:-2]
        res += ")"
        return res

    if is_update:
        res = ""
        for p in param_list:
            res +=  p +" = $"+ p + ", "
        res = res[:-2]
        return res

def warnign_old_folder():
    logger.warning("Please rename the folder that contains your endpoints to 'endpoints/' instead of 'api/'")
    logger.warning("Support for the 'api/' folder will be dropped in the future.")