import {useAuth} from "../services/AuthContext";
import {UploadWorkflowDesk} from "./UploadWorkflowDesk";
export function ServerUploadWorkbench({admin=false}:{admin?:boolean}){
  const {user,loading}=useAuth();
  return <UploadWorkflowDesk key={(user?.id??"guest")+":"+(user?.role??"")+":"+admin} admin={admin} user={user} authLoading={loading}/>;
}
