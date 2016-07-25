/**
 * 总服务，用于处理数据(ajax等)
 */
var angular = require('angular')

var baseservice = angular.module('baseService', []);
var getAuthtokenUrl = 'http://localhost:3001/sessions/create'

baseservice.factory('BaseService', ['$rootScope', '$http', '$q', function($rootScope,$http){
	
	//复写$http的ajax常用方法GET,POST
	function GET(url, params) {
		return $http({
			method: 'GET',
			url: url,
			params: params
		});
	}

	function POST(url, params) {
		return $http.post(url, params);
	}

	function JSONP(url, params) {
		return $http({
			method: 'JSONP',
			url: url,
			params: params
		})
	}


	return {
		POST: POST,
		GET: GET,
		JSONP: JSONP
	}
}])

baseservice.factory('UserService', ['BaseService', function(BaseService){
   
   //用户状态处理
	var user = {
		login: function(username, password) {
			return BaseService.POST(getAuthtokenUrl, {
				username: username,
				password: password
			});
		},
		logout: function() {
			return BaseService.POST('/api/user/logout')
		} 
	}
	return user;
}])

baseservice.factory('AuthenticationService', ['$rootScope', function($rootScope){
	var auth = {
		isLogged: false
	}

	return auth;
}])

baseservice.factory('TokenInterceptor', ['$q', '$window', '$location', 'AuthenticationService', function($q, $window, $location, AuthenticationService){
	return {
		request: function(config) {
			config.headers = config.headers || {};
			if($window.sessionStorage.token) {
				config.headers.Authorization = 'Bearer' + $window.sessionStorage.token
			}

			return config;
		},
		requestError: function(rejection) {
			return $q.reject(rejection)
		},
		response: function(response) {
			if (response != null && response.status == 200 && $window.sessionStorage.token && !AuthenticationService.isLogged) {
				AuthenticationService.isLogged = true
			}

			return response || $q.when(response)
		},
		responseError: function(rejection) {
			if(rejection != null && rejection.status == 401 && ($window.sessionStorage.token || AuthenticationService.isLogged)){
				delete $window.sessionStorage.token;
				AuthenticationService.isLogged = false;
				$location.path('/login')
			}
			return $q.reject(rejection)
		}

	};
}])